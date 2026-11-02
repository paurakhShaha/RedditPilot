from __future__ import annotations

from datetime import datetime

import pytest

from app.db import utcnow
from app.models import Draft, PublishedPost, SchedulePlan, ScheduledPost
from app.security import encrypt_secret
from app.services.gemini import GeneratedPost
from app.services.scheduler import materialize_slots, retry_slot, run_tick
from tests.conftest import SAFE_BODY, approve_direct, make_draft

NOW = datetime(2026, 11, 1, 12, 0, 0)  # Sunday noon UTC


def generated():
    return GeneratedPost(
        title="A specific lesson from rebuilding a small data parser",
        body=SAFE_BODY,
        disclosure="Disclosure: I built Time Traveler Receipt, the site mentioned here.",
        link_url=None,
        relevance="Data modelling and testing are on-topic for this community.",
        potential_rule_violations=[],
        promotional_intensity=1,
        warnings=[],
    )


def configure_schedule(settings_row, db, *, paused=False, frequency=1):
    settings_row.publishing_day = 0
    settings_row.publishing_time = "10:00"
    settings_row.timezone = "Asia/Kathmandu"
    settings_row.weekly_frequency = frequency
    settings_row.scheduling_paused = paused
    db.commit()


def make_plan(db, project, subreddit, *, enabled=True):
    plan = SchedulePlan(
        project_id=project.id,
        subreddit_id=subreddit.id,
        objective="Share a development story",
        post_type="Text post",
        topic_hint="A specific parser lesson",
        enabled=enabled,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def test_materialize_slots_is_idempotent(db, settings_row, project, subreddit):
    configure_schedule(settings_row, db)
    make_plan(db, project, subreddit)
    first = materialize_slots(db, NOW)
    second = materialize_slots(db, NOW)
    assert first >= 1
    assert second == 0
    slots = db.query(ScheduledPost).all()
    assert len(slots) == first
    starts = [slot.slot_start for slot in slots]
    assert len(starts) == len(set(starts))


def test_scheduler_generates_review_draft_and_never_publishes(
    db, settings_row, project, subreddit, monkeypatch
):
    configure_schedule(settings_row, db)
    settings_row.gemini_api_key_enc = encrypt_secret("fake")
    db.commit()
    make_plan(db, project, subreddit)
    monkeypatch.setattr("app.services.scheduler.generate_post", lambda **_: generated())

    result = run_tick(db, NOW)
    assert result["generated"] == 1, result
    assert result["paused"] is False
    draft = db.query(Draft).one()
    assert draft.status == "Pending Review"
    assert draft.source == "scheduled"
    slot = db.query(ScheduledPost).filter(ScheduledPost.draft_id == draft.id).one()
    assert slot.status == "draft_ready"
    assert db.query(PublishedPost).count() == 0

    # Running again must not duplicate the slot or the draft.
    run_tick(db, NOW)
    assert db.query(Draft).count() == 1
    assert db.query(ScheduledPost).count() == result["materialized"]


def test_paused_scheduler_creates_nothing(db, settings_row, project, subreddit):
    configure_schedule(settings_row, db, paused=True)
    make_plan(db, project, subreddit)
    result = run_tick(db, NOW)
    assert result["paused"] is True
    assert db.query(ScheduledPost).count() == 0
    assert db.query(Draft).count() == 0


def test_scheduler_without_key_fails_slot_with_actionable_error(
    db, settings_row, project, subreddit, monkeypatch
):
    configure_schedule(settings_row, db)
    make_plan(db, project, subreddit)
    monkeypatch.setattr(
        "app.services.scheduler.generate_post",
        lambda **_: pytest.fail("Gemini must not be called without a key"),
    )
    run_tick(db, NOW)
    slot = db.query(ScheduledPost).filter(ScheduledPost.status == "failed").one()
    assert "Gemini API key" in slot.error
    assert db.query(Draft).count() == 0


def test_retry_slot_after_configuring_key(db, settings_row, project, subreddit, monkeypatch):
    configure_schedule(settings_row, db)
    make_plan(db, project, subreddit)
    run_tick(db, NOW)
    slot = db.query(ScheduledPost).filter(ScheduledPost.status == "failed").one()
    settings_row.gemini_api_key_enc = encrypt_secret("fake")
    db.commit()
    monkeypatch.setattr("app.services.scheduler.generate_post", lambda **_: generated())
    result = retry_slot(db, slot.id)
    assert result["ok"] is True
    assert result["draft_id"]
    db.refresh(slot)
    assert slot.status == "draft_ready"


def test_plan_disabled_does_not_generate(db, settings_row, project, subreddit, monkeypatch):
    configure_schedule(settings_row, db)
    settings_row.gemini_api_key_enc = encrypt_secret("fake")
    db.commit()
    make_plan(db, project, subreddit, enabled=False)
    run_tick(db, NOW)
    assert db.query(Draft).count() == 0


def test_frequency_creates_multiple_weekly_slots(db, settings_row, project, subreddit):
    configure_schedule(settings_row, db, frequency=3)
    make_plan(db, project, subreddit)
    materialize_slots(db, NOW)
    slots = db.query(ScheduledPost).all()
    assert len(slots) >= 10  # five weeks, three slots per week (minus stale)
    for slot in slots:
        assert slot.status == "planned"


def test_paused_schedule_blocks_publishing_scheduled_draft(
    client, db, settings_row, project, subreddit
):
    configure_schedule(settings_row, db, paused=True)
    plan = make_plan(db, project, subreddit)
    slot = ScheduledPost(
        project_id=project.id,
        subreddit_id=subreddit.id,
        slot_start=utcnow(),
        status="approved",
        objective=plan.objective,
        post_type="Text post",
    )
    db.add(slot)
    db.commit()
    draft = make_draft(db, project, subreddit)
    slot.draft_id = draft.id
    db.commit()
    approve_direct(db, draft)

    response = client.post(f"/api/drafts/{draft.id}/publish/manual/prepare")
    assert response.status_code == 409
    assert "paused" in response.json()["detail"].lower()


def test_schedule_plan_api_rejects_prohibited_subreddit(
    client, db, settings_row, project, subreddit
):
    subreddit.self_promotion_policy = "prohibited"
    db.commit()
    response = client.put(
        f"/api/schedule/plan/{project.id}",
        json={
            "subreddit_id": subreddit.id,
            "objective": "Share a development story",
            "post_type": "Text post",
            "topic_hint": "",
            "enabled": True,
        },
    )
    assert response.status_code == 409
    assert "prohibits promotional" in response.json()["detail"]
