"""Gemini content generation with structured JSON, validation and retries.

The AI never approves or publishes anything. It only proposes content, which is
stored as a Pending Review draft with deterministic compliance warnings.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.config import settings as app_settings
from app.enums import SelfPromotionPolicy
from app.models import Project, Subreddit, UserSettings

logger = logging.getLogger("redditpilot.gemini")


class GeminiError(Exception):
    """A user-facing generation failure."""


class GeminiPolicyError(GeminiError):
    """Generation was refused because of community policy."""


class GeneratedPost(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    body: str = Field(min_length=80)
    disclosure: str = ""
    link_url: str | None = None
    relevance: str = ""
    potential_rule_violations: list[str] = Field(default_factory=list)
    promotional_intensity: int = Field(default=0, ge=0, le=5)
    warnings: list[str] = Field(default_factory=list)


SYSTEM_RULES = """You write Reddit posts for an independent developer who runs a small project.

Hard rules:
- Write like a real, specific human indie developer, not a marketer. Plain, concrete language.
- Never fabricate statistics, user counts, testimonials, revenue, metrics or engagement.
- Never pretend to be a customer, create fake conversations, fake accounts or fake anecdotes.
- Never use clickbait, hype, engagement bait, or excessive emojis.
- Never make misleading or unverifiable claims. If unsure, omit the claim.
- Clearly disclose the author's relationship to the project whenever it is mentioned.
- Respect the community rules provided. If promotion or links are prohibited, do not promote or link.
- Prefer genuine value: a lesson, a concrete build story, a question, or useful technical detail.
- Do not write generic marketing copy. No "revolutionary", "game-changing", "10x", "unlock", "supercharge".
- Do not spin an existing post. Find a distinct, specific angle for this community.
- A link is optional and must never be the point of the post.
- Reddit Markdown is allowed. Do not include a title inside the body.

Return ONLY a JSON object with these keys:
title (string), body (string, full Markdown post body), disclosure (string, first-person
statement of relationship, empty only if nothing promotional is mentioned), link_url
(string or null), relevance (string, why this fits this community's rules and interests),
potential_rule_violations (array of strings), promotional_intensity (integer 0-5),
warnings (array of strings, honest risks a human should check).
"""


def _recent_titles(project_id: int) -> list[str]:
    # Filled by the router from the DB; kept as an argument there. This helper
    # exists so the prompt builder stays free of DB access.
    return []



def build_prompt(
    *,
    project: Project,
    subreddit: Subreddit,
    objective: str,
    topic: str,
    post_type: str,
    link_preference: str,
    additional_notes: str,
    preferences: UserSettings,
    recent_titles: list[str],
) -> str:
    rules = "\n".join(f"- {r.title}: {r.detail}" for r in subreddit.rules) or "- No rules entered. Extra caution required."
    host = re.sub(r"^https?://(www\.)?", "", project.website_url).split("/")[0]
    recent = "\n".join(f"- {title}" for title in recent_titles[:8]) or "- None"

    link_instruction = {
        "none": "Do NOT include any link to the project. Do not put the project URL anywhere.",
        "optional": "Include the project link only if it genuinely adds value. Disclosure is mandatory if you do.",
        "preferred": "Include the project link once, in context, near the end. Disclosure is mandatory. Never make the link the main point.",
    }[link_preference]

    policy_note = {
        SelfPromotionPolicy.PROHIBITED.value: (
            "CRITICAL: this community prohibits promotional content. Do not mention or link "
            "the project at all. Write a purely value-first contribution. If that is impossible, "
            "say so in warnings."
        ),
        SelfPromotionPolicy.RESTRICTED.value: (
            "This community restricts self-promotion. Keep any project mention minimal, disclose it, "
            "and check flair/account requirements before posting."
        ),
        SelfPromotionPolicy.ALLOWED_WITH_DISCLOSURE.value: (
            "Self-promotion is allowed with disclosure. Still lead with value."
        ),
        SelfPromotionPolicy.UNKNOWN.value: (
            "The self-promotion policy is unknown. Be conservative: no hard sell, disclose any mention."
        ),
    }[subreddit.self_promotion_policy]

    return f"""Create one ({post_type}) Reddit post.

PROJECT CONTEXT
Name: {project.name}
Website: {project.website_url}
What it is: {project.description}
Target audience: {project.target_audience}
Category: {project.product_category}
USP: {project.unique_selling_proposition}
Features: {project.features}
Pricing: {project.pricing_info or "not provided"}
Brand voice: {project.brand_voice}
Marketing objectives: {project.marketing_objectives}
Required disclosure wording (adapt naturally, keep meaning): {project.disclosure_statement or "State clearly that you built the project."}
Restricted claims/topics (never include): {project.restricted_claims or "none specified"}

COMMUNITY
r/{subreddit.name}
Description: {subreddit.description}
Self-promotion policy: {subreddit.self_promotion_policy}
Links policy: {subreddit.links_policy}
Allowed post types: {", ".join(subreddit.allowed_post_types) or "unknown"}
Rules:
{rules}
Notes: {subreddit.notes or "none"}

REQUEST
Objective: {objective}
Post type: {post_type}
Topic / angle: {topic}
Link preference: {link_instruction}
Extra instructions: {additional_notes or "none"}
User's generation preferences: temperature {preferences.generation_temperature}, avoid emojis={preferences.avoid_emojis}.
Additional global notes: {preferences.extra_generation_notes or "none"}

RECENT TITLES (do not repeat these angles)
{recent}

POLICY
{policy_note}
Project domain: {host}. Do not invent metrics, quotes or user stories.

Before returning JSON, self-check: Does this read like a real dev? Is the title specific?
Is every factual claim verifiable or clearly framed as personal experience? Is the disclosure
unambiguous? Would a moderator consider this on-topic and non-spammy? If not, fix it."""


def _extract_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end <= start:
            raise GeminiError("Gemini returned a response that was not valid JSON. Try generating again.")
        try:
            parsed = json.loads(raw[start : end + 1])
        except json.JSONDecodeError as exc:
            raise GeminiError("Gemini returned malformed JSON. Try generating again.") from exc
    if not isinstance(parsed, dict):
        raise GeminiError("Gemini returned JSON in an unexpected format. Try generating again.")
    return parsed


def parse_generated_post(text: str) -> GeneratedPost:
    data = _extract_json(text)
    try:
        post = GeneratedPost.model_validate(data)
    except ValidationError as exc:
        fields = ", ".join(
            ".".join(str(part) for part in error["loc"]) for error in exc.errors()[:4]
        )
        raise GeminiError(f"Gemini's response failed validation ({fields}). Try generating again.") from exc

    post.title = re.sub(r"\s+", " ", post.title).strip()
    post.body = post.body.strip()
    post.disclosure = (post.disclosure or "").strip()
    if post.link_url:
        post.link_url = post.link_url.strip()
        if not post.link_url.startswith(("http://", "https://")):
            post.link_url = None
    return post


def _call_model(    *,
    api_key: str,
    model: str,
    prompt: str,
    temperature: float,
    timeout: int,
    repair_note: str = "",
) -> str:
    """Call the official google-genai SDK.

    Kept as a tiny function so tests can monkeypatch it without network access.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:  # pragma: no cover
        raise GeminiError("The google-genai package is not installed. Run pip install -r requirements.txt.") from exc

    try:
        client = genai.Client(api_key=api_key)
        contents = prompt if not repair_note else f"{prompt}\n\nCORRECTION: {repair_note}"
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_RULES,
                response_mime_type="application/json",
                temperature=temperature,
                max_output_tokens=4096,
            ),
        )
        text = getattr(response, "text", None)
        if not text:
            raise GeminiError("Gemini returned an empty response. Try again in a moment.")
        return text
    except GeminiError:
        raise
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        lowered = message.lower()
        logger.warning("Gemini request failed: %s", message[:500])
        if "api key" in lowered or "permission" in lowered or "unauthorized" in lowered or "401" in lowered:
            raise GeminiError(
                "Gemini rejected the API key. Check the key in Settings and try again."
            ) from exc
        if "429" in lowered or "rate" in lowered or "quota" in lowered:
            raise GeminiError(
                "Gemini rate limit or quota reached. Wait a little and try again."
            ) from exc
        if "timeout" in lowered or "deadline" in lowered:
            raise GeminiError("Gemini timed out. Try again; your draft was not saved.") from exc
        raise GeminiError(
            "Gemini could not generate this draft. Check your connection and API key, then try again."
        ) from exc


def generate_post(    *,
    project: Project,
    subreddit: Subreddit,
    objective: str,
    topic: str,
    post_type: str,
    link_preference: str,
    additional_notes: str,
    preferences: UserSettings,
    recent_titles: list[str],
    api_key: str | None,
    model: str | None = None,
    max_attempts: int = 3,
) -> GeneratedPost:
    if not api_key:
        raise GeminiError(
            "No Gemini API key is configured. Add one in Settings, or set GEMINI_API_KEY in .env."
        )
    if subreddit.self_promotion_policy == SelfPromotionPolicy.PROHIBITED.value and link_preference != "none":
        raise GeminiPolicyError(
            "This community prohibits promotional content, so a linked draft is blocked. "
            "Choose 'No link' or pick a different community."
        )

    model = model or app_settings.default_gemini_model
    prompt = build_prompt(
        project=project,
        subreddit=subreddit,
        objective=objective,
        topic=topic,
        post_type=post_type,
        link_preference=link_preference,
        additional_notes=additional_notes,
        preferences=preferences,
        recent_titles=recent_titles,
    )

    last_error: GeminiError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            text = _call_model(
                api_key=api_key,
                model=model,
                prompt=prompt,
                temperature=preferences.generation_temperature,
                timeout=app_settings.gemini_timeout_seconds,
                repair_note="Return strict JSON only." if attempt > 1 else "",
            )
            post = parse_generated_post(text)
            if preferences.avoid_emojis and re.search(
                r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", post.title + post.body
            ):
                post.warnings.append(
                    "Emoji review: generation prefers no emojis; remove any that slipped through."
                )

            if link_preference == "none":
                post.link_url = None
                domain = re.sub(r"^https?://(www\.)?", "", project.website_url).split("/")[0]
                post.body = re.sub(rf"https?://(www\.)?{re.escape(domain)}[^\s)]*", "", post.body).strip()
            if post.link_url and project.website_url and not post.link_url.startswith("http"):
                post.link_url = None
            return post
        except GeminiError as exc:
            last_error = exc
            if attempt < max_attempts and ("JSON" in str(exc) or "validation" in str(exc)):
                time.sleep(min(2.0, 0.4 * attempt) + random.uniform(0, 0.2))
                continue
            raise
    raise last_error or GeminiError("Gemini generation failed. Try again.")


def test_gemini_connection(api_key: str, model: str) -> str:
    """Cheap connectivity check used by Settings. Returns the model name."""
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:  # pragma: no cover
        raise GeminiError("The google-genai package is not installed.") from exc
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents='Reply with exactly this JSON: {"ok": true}',
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=32,
                temperature=0,
            ),
        )
        if not getattr(response, "text", None):
            raise GeminiError("Gemini returned an empty response.")
        return model
    except GeminiError:
        raise
    except Exception as exc:  # noqa: BLE001
        message = str(exc).lower()
        if "api key" in message or "401" in message or "permission" in message:
            raise GeminiError("Gemini rejected the API key. Check it and try again.") from exc
        if "429" in message or "quota" in message:
            raise GeminiError("Gemini quota or rate limit reached. Try again later.") from exc
        raise GeminiError("Could not reach Gemini with this key and model.") from exc
