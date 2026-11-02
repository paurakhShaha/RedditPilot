from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.db import utcnow
from app.models import Approval, Draft, PublishedPost
from app.services.settings_service import save_reddit_credentials
from tests.conftest import approve_direct, make_draft

MANUAL_URL = "https://www.reddit.com/r/webdev/comments/manual1/post_title/"


def test_manual_publish_requires_approval(client, db, settings_row, project, subreddit):
    draft = make_draft(db, project, subreddit)
    response = client.post(f"/api/drafts/{draft.id}/publish/manual/prepare")
    assert response.status_code == 409
    assert "not approved" in response.json()["detail"].lower()
    assert db.query(PublishedPost).count() == 0


def test_manual_publish_records_url_and_cannot_publish_twice(
    client, db, settings_row, project, subreddit
):
    draft = make_draft(db, project, subreddit)
    approve_direct(db, draft)
    prepared = client.post(f"/api/drafts/{draft.id}/publish/manual/prepare")
    assert prepared.status_code == 200, prepared.text
    payload = prepared.json()
    assert payload["submit_url"].startswith("https://www.reddit.com/r/webdev/submit?")
    assert "Disclosure:" in payload["body"]
    assert payload["disclosure_included"] is True

    confirmed = client.post(
        f"/api/drafts/{draft.id}/publish/manual/confirm",
        json={"url": MANUAL_URL, "note": "Published by hand"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["published_post"]["status"] == "published"
    assert confirmed.json()["draft"]["status"] == "Published"
    assert db.query(PublishedPost).count() == 1

    again = client.post(
        f"/api/drafts/{draft.id}/publish/manual/confirm",
        json={"url": MANUAL_URL},
    )
    assert again.status_code == 409


def test_manual_publish_rejects_wrong_subreddit_url(client, db, settings_row, project, subreddit):
    draft = make_draft(db, project, subreddit)
    approve_direct(db, draft)
    response = client.post(
        f"/api/drafts/{draft.id}/publish/manual/confirm",
        json={"url": "https://www.reddit.com/r/other/comments/abc123/title/"},
    )
    assert response.status_code == 422
    assert db.query(PublishedPost).count() == 0


def test_manual_publish_weekly_limit(client, db, settings_row, project, subreddit):
    first = make_draft(db, project, subreddit, title="First weekly post")
    approve_direct(db, first)
    client.post(
        f"/api/drafts/{first.id}/publish/manual/confirm",
        json={"url": MANUAL_URL},
    )
    second = make_draft(
        db,
        project,
        subreddit,
        title="Second weekly post",
        body="A completely different post about testing a parser with legacy data formats. " * 4,
    )
    approve_direct(db, second)
    response = client.post(f"/api/drafts/{second.id}/publish/manual/prepare")
    assert response.status_code == 409
    assert "Weekly limit" in response.json()["detail"]


def test_api_publishing_disabled_by_default(client, db, settings_row, project, subreddit):
    draft = make_draft(db, project, subreddit)
    approve_direct(db, draft)
    response = client.post(
        f"/api/drafts/{draft.id}/publish/api", json={"confirmation": True}
    )
    assert response.status_code == 403
    assert "Manual" in response.json()["detail"] or "disabled" in response.json()["detail"]
    assert db.query(PublishedPost).count() == 0
    settings_payload = client.get("/api/settings").json()
    assert settings_payload["api_publishing_enabled"] is False
    assert settings_payload["publishing_mode"] == "manual"


def test_api_publish_requires_final_confirmation(client, db, settings_row, project, subreddit):
    draft = make_draft(db, project, subreddit)
    approve_direct(db, draft)
    response = client.post(f"/api/drafts/{draft.id}/publish/api", json={"confirmation": False})
    assert response.status_code == 422


def test_enabling_api_requires_acknowledgement(client, db, settings_row):
    response = client.patch("/api/settings", json={"api_publishing_enabled": True})
    assert response.status_code == 422
    assert "acknowledgement" in response.json()["detail"].lower()
    ok = client.patch(
        "/api/settings",
        json={"api_publishing_enabled": True, "api_enable_acknowledged": True},
    )
    assert ok.status_code == 200
    assert ok.json()["api_publishing_enabled"] is True


def test_api_publish_success_with_mocked_reddit(client, db, settings_row, project, subreddit, monkeypatch):
    draft = make_draft(db, project, subreddit)
    approve_direct(db, draft)
    settings_row.publishing_mode = "api"
    settings_row.api_publishing_enabled = True
    save_reddit_credentials(
        db,
        {
            "client_id": "client",
            "client_secret": "secret",
            "username": "testuser",
            "password": "password",
            "user_agent": "redditpilot-test/1.0",
        },
    )

    submission = SimpleNamespace(id="api123", url="https://www.reddit.com/r/webdev/comments/api123/title/")

    class FakeReddit:
        @property
        def user(self):
            return SimpleNamespace(me=lambda: SimpleNamespace(name="testuser"))

        def subreddit(self, name):
            assert name == "webdev"
            return SimpleNamespace(submit=lambda **kwargs: submission)

    monkeypatch.setattr("app.services.publishing.build_reddit", lambda creds: FakeReddit())
    response = client.post(f"/api/drafts/{draft.id}/publish/api", json={"confirmation": True})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["published_post"]["status"] == "published"
    assert payload["published_post"]["reddit_post_id"] == "api123"
    assert payload["draft"]["status"] == "Published"
    post = db.query(PublishedPost).one()
    assert post.mode == "api"
    assert post.url == submission.url


def test_api_publish_authentication_failure_records_nothing(
    client, db, settings_row, project, subreddit, monkeypatch
):
    draft = make_draft(db, project, subreddit)
    approve_direct(db, draft)
    settings_row.publishing_mode = "api"
    settings_row.api_publishing_enabled = True
    save_reddit_credentials(
        db,
        {
            "client_id": "client",
            "client_secret": "secret",
            "username": "testuser",
            "password": "password",
            "user_agent": "redditpilot-test/1.0",
        },
    )

    class FakeReddit:
        @property
        def user(self):
            def fail():
                raise RuntimeError("invalid grant")

            return SimpleNamespace(me=fail)

    monkeypatch.setattr("app.services.publishing.build_reddit", lambda creds: FakeReddit())
    response = client.post(f"/api/drafts/{draft.id}/publish/api", json={"confirmation": True})
    assert response.status_code == 400
    assert db.query(PublishedPost).count() == 0
    db.refresh(draft)
    assert draft.status == "Approved"


def test_api_uncertain_submission_is_not_retried(
    client, db, settings_row, project, subreddit, monkeypatch
):
    draft = make_draft(db, project, subreddit)
    approve_direct(db, draft)
    settings_row.publishing_mode = "api"
    settings_row.api_publishing_enabled = True
    save_reddit_credentials(
        db,
        {
            "client_id": "client",
            "client_secret": "secret",
            "username": "testuser",
            "password": "password",
            "user_agent": "redditpilot-test/1.0",
        },
    )

    class FakeReddit:
        @property
        def user(self):
            return SimpleNamespace(me=lambda: SimpleNamespace(name="testuser"))

        def subreddit(self, name):
            def fail(**kwargs):
                raise TimeoutError("connection dropped after request was sent")

            return SimpleNamespace(submit=fail)

    monkeypatch.setattr("app.services.publishing.build_reddit", lambda creds: FakeReddit())
    response = client.post(f"/api/drafts/{draft.id}/publish/api", json={"confirmation": True})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["published_post"]["status"] == "uncertain"
    assert "will not retry" in payload["warning"]
    assert db.query(PublishedPost).count() == 1
    db.refresh(draft)
    assert draft.status == "Failed"

    # No automatic second submission is possible.
    again = client.post(f"/api/drafts/{draft.id}/publish/api", json={"confirmation": True})
    assert again.status_code == 409

    # The user can resolve the uncertainty without recording a fake URL.
    post_id = payload["published_post"]["id"]
    resolved = client.post(
        f"/api/published/{post_id}/resolve",
        json={"outcome": "not_published", "note": "Checked profile; nothing was posted"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["draft_status"] == "Approved"
    assert db.query(PublishedPost).count() == 0


def test_api_publish_requires_suitable_subreddit(client, db, settings_row, project, subreddit, monkeypatch):
    draft = make_draft(db, project, subreddit)
    approve_direct(db, draft)
    settings_row.publishing_mode = "api"
    settings_row.api_publishing_enabled = True
    subreddit.approval_status = "review"
    db.commit()
    save_reddit_credentials(
        db,
        {
            "client_id": "client",
            "client_secret": "secret",
            "username": "testuser",
            "password": "password",
            "user_agent": "redditpilot-test/1.0",
        },
    )
    called = {"value": False}

    def factory(creds):
        called["value"] = True
        return SimpleNamespace()

    monkeypatch.setattr("app.services.publishing.build_reddit", factory)
    response = client.post(f"/api/drafts/{draft.id}/publish/api", json={"confirmation": True})
    assert response.status_code == 409
    assert "Suitable" in response.json()["detail"]
    assert called["value"] is False
    assert db.query(PublishedPost).count() == 0
