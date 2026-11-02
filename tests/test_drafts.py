from __future__ import annotations

import pytest

from app.models import Draft, DraftRevision
from app.security import encrypt_secret
from app.services.gemini import GeneratedPost
from tests.conftest import SAFE_BODY, approve_direct, make_draft


@pytest.fixture()
def gemini_key(db, settings_row):
    settings_row.gemini_api_key_enc = encrypt_secret("test-api-key")
    db.commit()
    return "test-api-key"


def generated(**overrides):
    data = {
        "title": "The parsing bug that taught me to store prices in cents",
        "body": SAFE_BODY,
        "disclosure": "Disclosure: I built Time Traveler Receipt, the site mentioned here.",
        "link_url": None,
        "relevance": "A data-modeling story relevant to web developers.",
        "potential_rule_violations": [],
        "promotional_intensity": 1,
        "warnings": [],
    }
    data.update(overrides)
    return GeneratedPost(**data)


def test_generate_draft_persists_and_is_pending(client, db, gemini_key, project, subreddit, monkeypatch):
    monkeypatch.setattr("app.routers.drafts.generate_post", lambda **_: generated())
    response = client.post(
        "/api/drafts/generate",
        json={
            "project_id": project.id,
            "subreddit_id": subreddit.id,
            "objective": "Share a development story",
            "topic": "Parsing historical prices",
            "post_type": "Text post",
            "link_preference": "none",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "Pending Review"
    assert body["title"]
    assert body["revision_count"] == 1
    assert db.query(Draft).count() == 1
    assert db.query(DraftRevision).count() == 1


def test_generate_without_key_returns_clear_error(client, db, settings_row, project, subreddit):
    response = client.post(
        "/api/drafts/generate",
        json={
            "project_id": project.id,
            "subreddit_id": subreddit.id,
            "objective": "Share a development story",
            "topic": "Anything specific",
            "post_type": "Text post",
            "link_preference": "none",
        },
    )
    assert response.status_code == 400
    assert "Gemini API key" in response.json()["detail"]
    assert db.query(Draft).count() == 0


def test_generation_for_prohibited_subreddit_with_link_blocked(
    client, db, gemini_key, project, subreddit, monkeypatch
):
    subreddit.self_promotion_policy = "prohibited"
    subreddit.approval_status = "suitable"
    db.commit()
    called = {"value": False}

    def fake_generate(**_):
        called["value"] = True
        return generated()

    monkeypatch.setattr("app.routers.drafts.generate_post", fake_generate)
    response = client.post(
        "/api/drafts/generate",
        json={
            "project_id": project.id,
            "subreddit_id": subreddit.id,
            "objective": "Share a useful resource",
            "topic": "Historical prices",
            "post_type": "Text post",
            "link_preference": "optional",
        },
    )
    assert response.status_code == 409
    assert "prohibits promotional" in response.json()["detail"]
    assert called["value"] is False
    assert db.query(Draft).count() == 0


def test_generation_blocked_for_not_recommended_community(client, db, gemini_key, project, subreddit):
    subreddit.approval_status = "not_recommended"
    db.commit()
    response = client.post(
        "/api/drafts/generate",
        json={
            "project_id": project.id,
            "subreddit_id": subreddit.id,
            "objective": "Share a development story",
            "topic": "Historical prices",
            "post_type": "Text post",
            "link_preference": "none",
        },
    )
    assert response.status_code == 409


def test_approval_requires_attestation(client, db, settings_row, project, subreddit):
    draft = make_draft(db, project, subreddit)
    response = client.post(f"/api/drafts/{draft.id}/approve", json={"note": "ok"})
    assert response.status_code == 422
    assert db.get(Draft, draft.id).status == "Pending Review"


def test_approval_and_edit_invalidates_approval(client, db, settings_row, project, subreddit):
    draft = make_draft(db, project, subreddit)
    approved = client.post(
        f"/api/drafts/{draft.id}/approve", json={"attested": True, "note": "Reviewed rules"}
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "Approved"
    assert approved.json()["is_approved"] is True

    edited = client.patch(
        f"/api/drafts/{draft.id}",
        json={"title": "A materially revised and distinct title", "change_note": "Tightened title"},
    )
    assert edited.status_code == 200, edited.text
    payload = edited.json()
    assert payload["status"] == "Pending Review"
    assert payload["is_approved"] is False
    assert payload["approval"] is None
    assert payload["version"] == 2
    assert payload["revision_count"] == 2

    db.refresh(draft)
    assert draft.approvals
    assert all(not approval.is_valid for approval in draft.approvals)
    assert draft.approvals[0].invalidation_reason


def test_edit_does_not_invalidate_when_nothing_changed(client, db, settings_row, project, subreddit):
    draft = make_draft(db, project, subreddit)
    approve_direct(db, draft)
    response = client.patch(f"/api/drafts/{draft.id}", json={"change_note": "No actual change"})
    assert response.status_code == 200
    assert response.json()["status"] == "Approved"
    assert response.json()["is_approved"] is True


def test_approval_blocked_by_compliance_issue(client, db, settings_row, project, subreddit):
    draft = make_draft(db, project, subreddit, link_url="https://timetravelerreceipt.app/", disclosure="")
    response = client.post(f"/api/drafts/{draft.id}/approve", json={"attested": True})
    assert response.status_code == 409
    assert "blockers" in response.json()["detail"].lower()
    assert db.get(Draft, draft.id).status == "Pending Review"


def test_reject_draft(client, db, settings_row, project, subreddit):
    draft = make_draft(db, project, subreddit)
    response = client.post(f"/api/drafts/{draft.id}/reject", json={"reason": "Off-topic"})
    assert response.status_code == 200
    assert response.json()["status"] == "Rejected"


def test_regenerate_increments_version_and_clears_approval(
    client, db, gemini_key, project, subreddit, monkeypatch
):
    draft = make_draft(db, project, subreddit)
    approve_direct(db, draft)
    monkeypatch.setattr(
        "app.routers.drafts.generate_post",
        lambda **_: generated(title="A completely fresh angle on data validation"),
    )
    response = client.post(f"/api/drafts/{draft.id}/regenerate")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["version"] == 2
    assert payload["status"] == "Pending Review"
    assert payload["is_approved"] is False
    assert payload["title"] == "A completely fresh angle on data validation"


def test_duplicate_for_another_subreddit_creates_new_draft(
    client, db, gemini_key, project, subreddit, monkeypatch
):
    from app.models import Subreddit, SubredditRule
    from app.db import utcnow

    other = Subreddit(
        project_id=project.id,
        name="web_design",
        description="Design community",
        self_promotion_policy="allowed_with_disclosure",
        links_policy="allowed",
        allowed_post_types=["Text post"],
        approval_status="suitable",
        last_rules_verified_at=utcnow(),
    )
    other.rules.append(SubredditRule(title="Be useful", detail="No low-effort posts"))
    db.add(other)
    db.commit()
    parent = make_draft(db, project, subreddit)
    monkeypatch.setattr(
        "app.routers.drafts.generate_post",
        lambda **_: generated(title="A fresh design-focused angle on uncertainty"),
    )
    response = client.post(
        f"/api/drafts/{parent.id}/duplicate",
        json={"subreddit_id": other.id, "topic": "Showing uncertainty in UI"},
    )
    assert response.status_code == 201, response.text
    new = response.json()
    assert new["id"] != parent.id
    assert new["parent_draft_id"] == parent.id
    assert new["subreddit_id"] == other.id
    assert new["source"] == "duplicate"


def test_delete_draft_and_published_draft_cannot_be_deleted(
    client, db, settings_row, project, subreddit
):
    draft = make_draft(db, project, subreddit, title="Draft to delete")
    draft_id = draft.id
    response = client.delete(f"/api/drafts/{draft_id}")
    assert response.status_code == 200
    db.expire_all()
    assert db.get(Draft, draft_id) is None


def test_list_and_filter_drafts(client, db, settings_row, project, subreddit):
    make_draft(db, project, subreddit, title="One specific draft")
    make_draft(db, project, subreddit, title="Two specific draft")
    response = client.get("/api/drafts?status=Pending%20Review")
    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert response.json()["status_counts"]["Pending Review"] == 2


def test_draft_detail_includes_history(client, db, settings_row, project, subreddit):
    draft = make_draft(db, project, subreddit)
    client.patch(f"/api/drafts/{draft.id}", json={"body": SAFE_BODY + " An added concrete detail."})
    response = client.get(f"/api/drafts/{draft.id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == 2
    assert len(payload["approved_revisions"]) == 2
    assert payload["compliance"]["stage"] == "review"
