from __future__ import annotations

import json

from app.models import APIConnection
from app.security import decrypt_secret
from tests.conftest import make_draft


def test_gemini_key_is_encrypted_and_never_exposed(client, db, settings_row):
    response = client.patch(
        "/api/settings",
        json={
            "gemini_api_key": "super-secret-gemini-key",
            "gemini_model": "gemini-2.5-pro",
            "timezone": "Asia/Kathmandu",
            "publishing_time": "09:30",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["gemini_key_configured"] is True
    assert payload["gemini_model"] == "gemini-2.5-pro"
    assert "super-secret-gemini-key" not in response.text

    db.refresh(settings_row)
    assert settings_row.gemini_api_key_enc != "super-secret-gemini-key"
    assert decrypt_secret(settings_row.gemini_api_key_enc) == "super-secret-gemini-key"

    fetched = client.get("/api/settings")
    assert "super-secret-gemini-key" not in fetched.text


def test_reddit_credentials_are_encrypted_and_excluded_from_export(client, db, settings_row, project):
    response = client.patch(
        "/api/settings",
        json={
            "reddit": {
                "client_id": "client-123",
                "client_secret": "reddit-client-secret",
                "username": "some_redditor",
                "password": "reddit-password",
                "user_agent": "redditpilot/1.0 by u/some_redditor",
            }
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["reddit_credentials_configured"] is True
    assert "reddit-client-secret" not in response.text
    assert "reddit-password" not in response.text

    connection = db.query(APIConnection).one()
    assert connection.client_secret_enc != "reddit-client-secret"
    assert connection.password_enc != "reddit-password"
    assert decrypt_secret(connection.client_secret_enc) == "reddit-client-secret"
    assert decrypt_secret(connection.password_enc) == "reddit-password"

    export = client.get("/api/settings/export")
    assert export.status_code == 200
    assert "reddit-client-secret" not in export.text
    assert "reddit-password" not in export.text
    assert "super-secret" not in export.text
    body = export.json()
    assert any(item["id"] == project.id for item in body["projects"])


def test_clear_reddit_credentials(client, db, settings_row):
    client.patch(
        "/api/settings",
        json={"reddit": {"client_id": "x", "client_secret": "y", "user_agent": "ua"}},
    )
    cleared = client.patch("/api/settings", json={"clear_reddit_credentials": True})
    assert cleared.status_code == 200
    assert cleared.json()["reddit_credentials_configured"] is False
    connection = db.query(APIConnection).one()
    assert connection.client_secret_enc is None


def test_default_project_and_invalid_values(client, db, settings_row, project):
    response = client.patch("/api/settings", json={"default_project_id": project.id})
    assert response.status_code == 200
    assert response.json()["default_project_id"] == project.id
    bad_time = client.patch("/api/settings", json={"publishing_time": "25:90"})
    assert bad_time.status_code == 422
    bad_tz = client.patch("/api/settings", json={"timezone": "Mars/Olympus"})
    assert bad_tz.status_code == 422
    bad_day = client.patch("/api/settings", json={"publishing_day": 9})
    assert bad_day.status_code == 422


def test_backup_creates_downloadable_sqlite_file(client, db, settings_row):
    response = client.post("/api/settings/backup")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/octet-stream")
    assert response.content.startswith(b"SQLite format 3")

    # The dashboard downloads the backup with a GET request.
    download = client.get("/api/settings/backup")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/octet-stream")
    assert download.content.startswith(b"SQLite format 3")


def test_unknown_api_path_returns_json_404(client):
    response = client.get("/api/definitely-not-a-real-endpoint")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["detail"]


def test_activity_log_records_user_actions(client, db, settings_row, project, subreddit):
    draft = make_draft(db, project, subreddit)
    client.post(f"/api/drafts/{draft.id}/approve", json={"attested": True, "note": "ok"})
    response = client.get("/api/settings/activity")
    assert response.status_code == 200
    actions = [item["action"] for item in response.json()["items"]]
    assert "draft.approved" in actions


def test_export_contains_draft_history(client, db, settings_row, project, subreddit):
    draft = make_draft(db, project, subreddit)
    client.patch(f"/api/drafts/{draft.id}", json={"title": "A revised export title"})
    response = client.get("/api/settings/export")
    body = response.json()
    assert body["drafts"][0]["title"] == "A revised export title"
    assert body["revisions"]
    assert body["settings"]["gemini_key_configured"] is False
