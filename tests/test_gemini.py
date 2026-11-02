from __future__ import annotations

import json

import pytest

from app.services.gemini import (
    GeminiError,
    GeminiPolicyError,
    build_prompt,
    generate_post,
    parse_generated_post,
)


def valid_payload(**overrides):
    payload = {
        "title": "A concrete build story about messy price data",
        "body": (
            "I rebuilt the parser behind a small history project. The first version compared "
            "formatted strings, which failed on regional number formats. I switched to integer "
            "cents and added tests for several decades of prices. The interesting challenge was "
            "communicating uncertainty when the source data is only an estimate."
        ),
        "disclosure": "Disclosure: I built the project mentioned here.",
        "link_url": None,
        "relevance": "Data modeling and testing are relevant to this community.",
        "potential_rule_violations": ["Weekend showcase rule may apply"],
        "promotional_intensity": 1,
        "warnings": ["Check flair"],
    }
    payload.update(overrides)
    return payload


def test_parse_plain_json():
    post = parse_generated_post(json.dumps(valid_payload()))
    assert post.title.startswith("A concrete")
    assert post.promotional_intensity == 1


def test_parse_fenced_json():
    text = "```json\n" + json.dumps(valid_payload()) + "\n```"
    post = parse_generated_post(text)
    assert post.disclosure


def test_parse_json_with_leading_prose():
    text = "Here is the draft:\n" + json.dumps(valid_payload())
    post = parse_generated_post(text)
    assert post.promotional_intensity == 1


def test_parse_malformed_json_raises():
    with pytest.raises(GeminiError):
        parse_generated_post("not json at all")


def test_parse_validation_error_raises():
    with pytest.raises(GeminiError):
        parse_generated_post(json.dumps(valid_payload(title="")))


def test_build_prompt_includes_rules_and_disclosure_requirements(project, subreddit, settings_row):
    prompt = build_prompt(
        project=project,
        subreddit=subreddit,
        objective="Share a development story",
        topic="Historical data",
        post_type="Text post",
        link_preference="optional",
        additional_notes="",
        preferences=settings_row,
        recent_titles=["Earlier title"],
    )
    assert "Show off Saturday" in prompt
    assert "do not invent" in prompt.lower()
    assert "Earlier title" in prompt
    assert "disclosure" in prompt.lower()


def test_generation_without_key_fails(project, subreddit, settings_row):
    with pytest.raises(GeminiError):
        generate_post(
            project=project,
            subreddit=subreddit,
            objective="Share a development story",
            topic="Data",
            post_type="Text post",
            link_preference="none",
            additional_notes="",
            preferences=settings_row,
            recent_titles=[],
            api_key=None,
        )


def test_generation_retries_on_invalid_json(monkeypatch, project, subreddit, settings_row):
    calls = {"count": 0}

    def fake_call(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return "this is not json"
        return json.dumps(valid_payload())

    monkeypatch.setattr("app.services.gemini._call_model", fake_call)
    monkeypatch.setattr("app.services.gemini.time.sleep", lambda *_: None)
    post = generate_post(
        project=project,
        subreddit=subreddit,
        objective="Share a development story",
        topic="Data",
        post_type="Text post",
        link_preference="none",
        additional_notes="",
        preferences=settings_row,
        recent_titles=[],
        api_key="fake-key",
    )
    assert calls["count"] == 2
    assert post.title


def test_link_is_removed_when_preference_is_none(monkeypatch, project, subreddit, settings_row):
    payload = valid_payload(
        link_url="https://timetravelerreceipt.app/",
        body=valid_payload()["body"] + " Link: https://timetravelerreceipt.app/",
    )
    monkeypatch.setattr("app.services.gemini._call_model", lambda **_: json.dumps(payload))
    post = generate_post(
        project=project,
        subreddit=subreddit,
        objective="Share a development story",
        topic="Data",
        post_type="Text post",
        link_preference="none",
        additional_notes="",
        preferences=settings_row,
        recent_titles=[],
        api_key="fake-key",
    )
    assert post.link_url is None
    assert "timetravelerreceipt.app" not in post.body


def test_prohibited_community_blocks_linked_generation(project, subreddit, settings_row):
    subreddit.self_promotion_policy = "prohibited"
    with pytest.raises(GeminiPolicyError):
        generate_post(
            project=project,
            subreddit=subreddit,
            objective="Share a useful resource",
            topic="Data",
            post_type="Text post",
            link_preference="preferred",
            additional_notes="",
            preferences=settings_row,
            recent_titles=[],
            api_key="fake-key",
        )
