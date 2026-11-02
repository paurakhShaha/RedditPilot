"""Compliance and safety engine.

Every warning and blocker here is shown in the dashboard before approval. The
engine is deterministic and does not call an AI. It deliberately fails closed:
unknown rules, missing disclosures and prohibited promotion are surfaced.
"""

from __future__ import annotations

import re
from datetime import timedelta
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.enums import (
    DraftStatus,
    LinksPolicy,
    PROMOTIONAL_OBJECTIVES,
    SelfPromotionPolicy,
    SubredditApproval,
)
from app.models import Draft, PublishedPost, Subreddit, UserSettings
from app.services.serialize import iso
from app.services.settings_service import get_gemini_key, get_settings_row

PROMO_PHRASES = [
    "check it out",
    "check out",
    "sign up",
    "try it out",
    "would love your feedback",
    "would love for you",
    "revolutionary",
    "game-changer",
    "game changer",
    "must-have",
    "must have",
    "10x",
    "best-in-class",
    "limited time",
    "don't miss",
    "unlock",
    "effortless",
    "seamless",
    "powerful",
    "transform",
    "crushing it",
    "supercharge",
    "take it to the next level",
]

CTA_PHRASES = ["check it out", "check out", "sign up", "try it", "visit my", "link in", "click"]

CLICKBAIT_PHRASES = [
    "you won't believe",
    "shocking",
    "mind-blowing",
    "this one trick",
    "secret to",
    "nobody talks about",
]

CLAIM_PATTERNS = [
    r"\b\d{1,3}(?:\.\d+)?\s?%\s+(?:of\s+)?(?:users|people|customers|developers|faster|more|better|increase|reduction|growth)",
    r"\b(?:thousands|millions|hundreds of thousands)\s+(?:of\s+)?(?:users|people|customers|developers|downloads)",
    r"\b(?:guarantee|guaranteed|proven to|scientifically|studies show)\b",
    r"\b(?:#1|number one)\s+(?:app|tool|platform|product)\b",
    r"\b(?:doubled|tripled|increased by)\s+\d+",
]

DISCLOSURE_HINTS = [
    "i built",
    "i made",
    "i'm the",
    "i am the",
    "my project",
    "my website",
    "my app",
    "disclosure",
    "founder",
    "creator",
    "developer of",
    "i created",
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _issue(code: str, severity: str, message: str, field: str | None = None) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message, "field": field}


def _find_restricted_claims(project) -> list[str]:
    raw = project.restricted_claims or ""
    parts = re.split(r"[\n;,]+", raw)
    return [p.strip() for p in parts if len(p.strip()) >= 3][:30]


def computed_promo_score(draft: Draft, settings_row: UserSettings) -> int:
    text = _normalize(f"{draft.title} {draft.body} {draft.disclosure}")
    score = 0
    if draft.link_url:
        score += 1
    website = (draft.project.website_url or "").lower() if draft.project else ""
    host = re.sub(r"^https?://(www\.)?", "", website).split("/")[0]
    if host and host in text:
        score += 1
    if draft.objective in PROMOTIONAL_OBJECTIVES:
        score += 1
    phrase_hits = sum(1 for phrase in PROMO_PHRASES if phrase in text)
    if phrase_hits >= 2:
        score += 1
    if phrase_hits >= 4:
        score += 1
    cta_hits = sum(1 for phrase in CTA_PHRASES if phrase in text)
    if cta_hits >= 2:
        score += 1
    return min(5, score)


def is_promotional(draft: Draft) -> bool:
    text = _normalize(f"{draft.title} {draft.body} {draft.disclosure}")
    website = (draft.project.website_url or "").lower() if draft.project else ""
    host = re.sub(r"^https?://(www\.)?", "", website).split("/")[0]
    return bool(
        draft.link_url
        or (host and host in text)
        or draft.objective in PROMOTIONAL_OBJECTIVES
        or draft.promotional_intensity >= 3
    )


def disclosure_present(draft: Draft) -> bool:
    disclosure = _normalize(draft.disclosure)
    if len(disclosure) >= 12:
        return True
    body = _normalize(draft.body)
    return any(hint in body for hint in DISCLOSURE_HINTS)


def duplicate_report(db: Session, draft: Draft) -> dict[str, Any]:
    """Compare against other drafts in the same project.

    Returns the strongest matches. The draft itself and rejected/archived drafts
    are ignored.
    """
    normalized_title = _normalize(draft.title)
    normalized_body = _normalize(draft.body)
    others = (
        db.query(Draft)
        .filter(
            Draft.project_id == draft.project_id,
            Draft.id != draft.id,
            Draft.status.notin_([DraftStatus.REJECTED.value, DraftStatus.ARCHIVED.value]),
        )
        .order_by(Draft.created_at.desc())
        .limit(150)
        .all()
    )
    exact_title: list[dict[str, Any]] = []
    similar_body: list[dict[str, Any]] = []
    for other in others:
        if _normalize(other.title) == normalized_title:
            exact_title.append(
                {
                    "draft_id": other.id,
                    "title": other.title,
                    "subreddit": other.subreddit.name if other.subreddit else "",
                    "status": other.status,
                }
            )
        ratio = SequenceMatcher(None, normalized_body[:4000], _normalize(other.body)[:4000]).ratio()
        if ratio >= 0.82:
            similar_body.append(
                {
                    "draft_id": other.id,
                    "title": other.title,
                    "similarity": round(ratio * 100, 1),
                    "status": other.status,
                }
            )
    similar_body.sort(key=lambda item: item["similarity"], reverse=True)
    return {"exact_title": exact_title[:5], "similar_body": similar_body[:5]}


def weekly_usage(db: Session, project_id: int, settings_row: UserSettings) -> dict[str, Any]:
    since = utcnow() - timedelta(days=7)
    count = (
        db.query(PublishedPost)
        .filter(
            PublishedPost.project_id == project_id,
            PublishedPost.status == "published",
            PublishedPost.published_at >= since,
        )
        .count()
    )
    return {
        "published_last_7_days": count,
        "limit": settings_row.weekly_frequency,
        "remaining": max(0, settings_row.weekly_frequency - count),
    }


def evaluate_draft(
    db: Session,
    draft: Draft,
    *,
    stage: str = "review",
    settings_row: UserSettings | None = None,
) -> dict[str, Any]:
    """Evaluate a draft for compliance.

    stage:
      - "generation": early feedback right after AI generation
      - "review": shown before approval (default)
      - "publish": strict, includes approval + weekly limit checks
    """
    settings_row = settings_row or get_settings_row(db)
    subreddit: Subreddit = draft.subreddit
    project = draft.project
    issues: list[dict[str, Any]] = []

    if not draft.title.strip():
        issues.append(_issue("missing_title", "blocker", "The draft has no title.", "title"))
    if len(draft.body.strip()) < 80:
        issues.append(
            _issue("body_too_short", "blocker", "The post body is too short to add genuine value.", "body")
        )

    promo_policy = subreddit.self_promotion_policy
    promotional = is_promotional(draft)
    promo_score = computed_promo_score(draft, settings_row)

    if promo_policy == SelfPromotionPolicy.PROHIBITED.value:
        if promotional:
            issues.append(
                _issue(
                    "promotion_prohibited",
                    "blocker",
                    "This community prohibits promotional content. Remove the project mention/link or choose a different community.",
                    "link_url",
                )
            )
        else:
            issues.append(
                _issue(
                    "promotion_prohibited_warning",
                    "warning",
                    "Promotion is prohibited here. Keep this post purely educational and do not mention the project.",
                )
            )
    elif promo_policy == SelfPromotionPolicy.UNKNOWN.value:
        issues.append(
            _issue(
                "promotion_policy_unknown",
                "warning",
                "The community's self-promotion policy is unknown. Verify the current rules before publishing.",
            )
        )
    elif promo_policy == SelfPromotionPolicy.RESTRICTED.value and promotional:
        issues.append(
            _issue(
                "promotion_restricted",
                "warning",
                "Promotion is restricted here. Check minimum account age, flair and disclosure requirements in the community rules.",
            )
        )

    if promotional and not disclosure_present(draft):
        issues.append(
            _issue(
                "missing_disclosure",
                "blocker",
                "Promotional content must clearly disclose your relationship with the project.",
                "disclosure",
            )
        )

    if subreddit.links_policy == LinksPolicy.NOT_ALLOWED.value and draft.link_url:
        issues.append(
            _issue(
                "links_not_allowed",
                "blocker",
                "This community does not allow links. Remove the link before approval.",
                "link_url",
            )
        )
    elif subreddit.links_policy == LinksPolicy.RESTRICTED.value and draft.link_url:
        issues.append(
            _issue(
                "links_restricted",
                "warning",
                "Links are restricted here. Confirm the post meets the community's link rules.",
                "link_url",
            )
        )
    elif subreddit.links_policy == LinksPolicy.UNKNOWN.value and draft.link_url:
        issues.append(
            _issue(
                "links_policy_unknown",
                "warning",
                "The community's links policy is unknown. Verify before publishing.",
            )
        )

    allowed_types = subreddit.allowed_post_types or []
    if allowed_types and draft.post_type not in allowed_types:
        issues.append(
            _issue(
                "post_type_not_allowed",
                "blocker" if stage == "publish" else "warning",
                f"'{draft.post_type}' is not in the allowed post types you recorded for this community: {', '.join(allowed_types)}.",
            )
        )

    if draft.link_url:
        project_host = re.sub(
            r"^https?://(www\.)?", "", (project.website_url or "").lower()
        ).split("/")[0]
        link_host = re.sub(r"^https?://(www\.)?", "", draft.link_url.lower()).split("/")[0]
        if project_host and link_host and project_host != link_host:
            issues.append(
                _issue(
                    "external_link",
                    "warning",
                    f"The link points to {link_host}, not the project website ({project_host}). Confirm it is relevant.",
                )
            )

    if promo_score > settings_row.max_promo_score:
        issues.append(
            _issue(
                "excessive_promotion",
                "blocker",
                f"Promotional intensity is {promo_score}/5, above your configured limit of {settings_row.max_promo_score}. Reduce calls to action and marketing language.",
            )
        )
    elif promo_score >= 3:
        issues.append(
            _issue(
                "promotional_tone",
                "warning",
                f"Promotional intensity is {promo_score}/5. Consider leading with more genuine value.",
            )
        )

    low_title = _normalize(draft.title)
    if low_title and low_title == low_title.upper() and len(low_title) > 12:
        issues.append(_issue("all_caps_title", "warning", "Avoid an all-caps title; it reads as clickbait."))
    for phrase in CLICKBAIT_PHRASES:
        if phrase in low_title:
            issues.append(
                _issue("clickbait_title", "warning", f"Title contains clickbait phrasing: '{phrase}'.")
            )
            break
    emoji_count = len(re.findall(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", draft.body + draft.title))
    if emoji_count > 2:
        issues.append(_issue("too_many_emojis", "warning", "Reduce emoji use; Reddit posts read better without them."))

    for pattern in CLAIM_PATTERNS:
        match = re.search(pattern, f"{draft.title} {draft.body}", re.IGNORECASE)
        if match:
            issues.append(
                _issue(
                    "unverified_claim",
                    "warning",
                    f"Possible unverified statistical claim: '{match.group(0)}'. Verify or remove it.",
                )
            )
            break

    for claim in _find_restricted_claims(project):
        if claim.lower() in _normalize(f"{draft.title} {draft.body} {draft.disclosure}"):
            issues.append(
                _issue(
                    "restricted_claim",
                    "blocker",
                    f"The draft contains a restricted claim from the project brief: '{claim}'.",
                )
            )

    if len(draft.body) > 40000:
        issues.append(_issue("body_too_long", "warning", "Reddit self-posts have a 40,000 character limit."))

    sentences = [s.strip().lower() for s in re.split(r"(?<=[.!?])\s+", draft.body) if len(s.strip()) > 25]
    if sentences:
        unique_ratio = len(set(sentences)) / len(sentences)
        if unique_ratio < 0.7:
            issues.append(
                _issue("repetitive_body", "warning", "The body repeats itself. Tighten it before approval.")
            )

    duplicates = duplicate_report(db, draft)
    if duplicates["exact_title"]:
        severity = "blocker" if stage == "publish" else "warning"
        issues.append(
            _issue(
                "duplicate_title",
                severity,
                f"Another draft already uses this title (draft #{duplicates['exact_title'][0]['draft_id']}). Use a distinct angle.",
            )
        )
    if duplicates["similar_body"]:
        top = duplicates["similar_body"][0]
        severity = "blocker" if stage == "publish" and top["similarity"] >= 92 else "warning"
        issues.append(
            _issue(
                "similar_body",
                severity,
                f"The body is {top['similarity']}% similar to draft #{top['draft_id']} ({top['status']}). Generate a genuinely different post.",
            )
        )

    if not draft.relevance.strip():
        issues.append(
            _issue("missing_relevance", "warning", "Add a short explanation of why this belongs in the community.")
        )

    verified_at = subreddit.last_rules_verified_at
    if not verified_at:
        issues.append(
            _issue(
                "rules_unverified",
                "warning",
                "You have not recorded a rules verification date for this community. Review the current rules first.",
            )
        )
    else:
        age = (utcnow() - verified_at).days
        if age > 180:
            issues.append(
                _issue(
                    "rules_stale",
                    "blocker" if stage == "publish" else "warning",
                    f"Subreddit rules were last verified {age} days ago. Re-check them before publishing.",
                )
            )
        elif age > 90:
            issues.append(
                _issue(
                    "rules_aging",
                    "warning",
                    f"Subreddit rules were last verified {age} days ago. Consider re-checking them.",
                )
            )

    if subreddit.approval_status == SubredditApproval.PROHIBITED.value:
        issues.append(
            _issue(
                "subreddit_prohibited",
                "blocker",
                "You marked this community as prohibiting promotional content. It cannot be published from RedditPilot.",
            )
        )
    elif subreddit.approval_status == SubredditApproval.NOT_RECOMMENDED.value:
        issues.append(
            _issue(
                "subreddit_not_recommended",
                "blocker",
                "You marked this community as not recommended. Change its status after re-reviewing the rules.",
            )
        )
    elif subreddit.approval_status == SubredditApproval.REVIEW.value:
        issues.append(
            _issue(
                "subreddit_needs_review",
                "warning",
                "This community still needs review. Confirm its rules before publishing.",
            )
        )

    if subreddit.min_account_age_days:
        issues.append(
            _issue(
                "account_age_requirement",
                "info",
                f"Community guidance: account should be at least {subreddit.min_account_age_days} days old.",
            )
        )
    if subreddit.min_karma:
        issues.append(
            _issue(
                "karma_requirement",
                "info",
                f"Community guidance: minimum karma is {subreddit.min_karma}.",
            )
        )

    if stage == "publish":
        if not draft.is_approved:
            issues.append(
                _issue(
                    "not_approved",
                    "blocker",
                    "This exact version has not been approved. Approve it after reviewing the content.",
                )
            )
        if draft.status == DraftStatus.PUBLISHED.value:
            issues.append(
                _issue("already_published", "blocker", "This draft has already been published.")
            )
        if draft.published_post:
            issues.append(
                _issue(
                    "existing_publication",
                    "blocker",
                    "A publication record already exists for this draft. It cannot be published twice.",
                )
            )
        published_same = (
            db.query(PublishedPost)
            .join(Draft, PublishedPost.draft_id == Draft.id)
            .filter(
                PublishedPost.project_id == draft.project_id,
                Draft.content_hash == draft.content_hash,
                Draft.id != draft.id,
            )
            .first()
        )
        if published_same:
            issues.append(
                _issue(
                    "already_published_content",
                    "blocker",
                    f"This exact content was already published in draft #{published_same.draft_id}.",
                )
            )

    usage = weekly_usage(db, draft.project_id, settings_row)
    if stage == "publish" and usage["remaining"] <= 0:
        issues.append(
            _issue(
                "weekly_limit",
                "blocker",
                f"Weekly limit reached ({usage['published_last_7_days']}/{usage['limit']} in the last 7 days). Wait for the next window.",
            )
        )
    elif usage["remaining"] <= 0:
        issues.append(
            _issue(
                "weekly_limit_warning",
                "warning",
                f"You have already published {usage['published_last_7_days']} post(s) in the last 7 days. The configured limit is {usage['limit']}/week.",
            )
        )

    blockers = sum(1 for issue in issues if issue["severity"] == "blocker")
    warnings = sum(1 for issue in issues if issue["severity"] == "warning")
    level = "blocked" if blockers else ("warning" if warnings else "ok")

    return {
        "stage": stage,
        "level": level,
        "issues": issues,
        "blockers": blockers,
        "warnings": warnings,
        "promotional_score": promo_score,
        "duplicates": duplicates,
        "weekly": usage,
        "rules_verified_age_days": (
            (utcnow() - subreddit.last_rules_verified_at).days
            if subreddit.last_rules_verified_at
            else None
        ),
        "evaluated_at": iso(utcnow()),
    }


def refresh_compliance(db: Session, draft: Draft, *, stage: str = "review") -> dict[str, Any]:
    report = evaluate_draft(db, draft, stage=stage)
    draft.compliance_snapshot = report
    draft.warnings = [i["message"] for i in report["issues"] if i["severity"] != "blocker"]
    draft.rule_violations = [i["message"] for i in report["issues"] if i["severity"] == "blocker"]
    return report


def api_publish_blockers(db: Session, draft: Draft) -> list[str]:
    """Extra eligibility checks specific to automated API publishing."""
    reasons: list[str] = []
    settings_row = get_settings_row(db)
    subreddit = draft.subreddit
    if settings_row.publishing_mode != "api":
        reasons.append("Publishing mode is set to Manual. Switch to API mode in Settings.")
    if not settings_row.api_publishing_enabled:
        reasons.append("API publishing is disabled. Enable it explicitly in Settings after reviewing the requirements.")
    if subreddit.approval_status != SubredditApproval.SUITABLE.value:
        reasons.append("The subreddit is not marked 'Suitable' after a rules review.")
    if subreddit.self_promotion_policy == SelfPromotionPolicy.PROHIBITED.value:
        reasons.append("The subreddit prohibits promotional content.")
    if not subreddit.last_rules_verified_at:
        reasons.append("Subreddit rules have never been verified.")
    elif (utcnow() - subreddit.last_rules_verified_at).days > 120:
        reasons.append("Subreddit rules verification is older than 120 days.")
    if not get_gemini_key(db):
        # Not required to publish, but this guards against a half-configured setup.
        pass
    report = evaluate_draft(db, draft, stage="publish", settings_row=settings_row)
    reasons.extend(
        issue["message"] for issue in report["issues"] if issue["severity"] == "blocker"
    )
    # Deduplicate while preserving order.
    return list(dict.fromkeys(reasons))
