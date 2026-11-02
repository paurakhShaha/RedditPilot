from __future__ import annotations

from app.models import Draft, Project, Subreddit, SubredditRule
from tests.conftest import make_draft


def project_payload(**overrides):
    data = {
        "name": "Test Project",
        "website_url": "https://example.com/",
        "description": "A useful description",
        "target_audience": "Developers",
        "product_category": "Web app",
        "unique_selling_proposition": "Solves a small problem",
        "features": "Feature one",
        "pricing_info": "Free",
        "brand_voice": "Direct",
        "marketing_objectives": "Find early users",
        "disclosure_statement": "I built this.",
        "restricted_claims": "No guarantees",
    }
    data.update(overrides)
    return data


def test_create_and_list_projects(client, db):
    created = client.post("/api/projects", json=project_payload())
    assert created.status_code == 201, created.text
    project = created.json()
    assert project["name"] == "Test Project"
    assert project["draft_count"] == 0
    settings = client.get("/api/settings").json()
    assert settings["default_project_id"] == project["id"]
    assert len(client.get("/api/projects").json()["items"]) == 1


def test_project_validation_rejects_bad_url(client, db):
    response = client.post("/api/projects", json=project_payload(website_url="not-a-url"))
    assert response.status_code == 422


def test_update_project(client, db, project):
    response = client.patch(f"/api/projects/{project.id}", json={"brand_voice": "Warm and precise"})
    assert response.status_code == 200
    assert response.json()["brand_voice"] == "Warm and precise"


def test_project_with_drafts_cannot_be_deleted(client, db, settings_row, project, subreddit):
    make_draft(db, project, subreddit)
    response = client.delete(f"/api/projects/{project.id}")
    assert response.status_code == 409


def test_create_subreddit_with_rules_and_verify(client, db, project):
    response = client.post(
        "/api/subreddits",
        json={
            "project_id": project.id,
            "name": "r/TestCommunity",
            "description": "A test community",
            "self_promotion_policy": "restricted",
            "links_policy": "not_allowed",
            "allowed_post_types": ["Text post", "Discussion"],
            "rules": [
                {"title": "Stay on topic", "detail": "Only relevant posts"},
                {"title": "No links", "detail": "Links are removed"},
            ],
            "approval_status": "review",
        },
    )
    assert response.status_code == 201, response.text
    subreddit = response.json()
    assert subreddit["name"] == "TestCommunity"
    assert len(subreddit["rules"]) == 2
    assert "Stay on topic" in subreddit["rules_text"]
    assert subreddit["last_rules_verified_at"] is None

    verified = client.post(f"/api/subreddits/{subreddit['id']}/verify")
    assert verified.status_code == 200
    assert verified.json()["last_rules_verified_at"] is not None


def test_duplicate_subreddit_for_project_rejected(client, db, project, subreddit):
    response = client.post(
        "/api/subreddits",
        json={
            "project_id": project.id,
            "name": "webdev",
            "self_promotion_policy": "unknown",
            "approval_status": "review",
            "rules": [],
        },
    )
    assert response.status_code == 409


def test_update_rules_replaces_list(client, db, project, subreddit):
    response = client.patch(
        f"/api/subreddits/{subreddit.id}",
        json={"rules": [{"title": "New rule", "detail": "Only one rule now"}], "approval_status": "suitable"},
    )
    assert response.status_code == 200
    assert len(response.json()["rules"]) == 1
    assert response.json()["rules"][0]["title"] == "New rule"


def test_subreddit_with_drafts_cannot_be_deleted(client, db, settings_row, project, subreddit):
    make_draft(db, project, subreddit)
    response = client.delete(f"/api/subreddits/{subreddit.id}")
    assert response.status_code == 409


def test_non_ascii_subreddit_name_rejected(client, db, project):
    response = client.post(
        "/api/subreddits",
        json={"project_id": project.id, "name": "bad name!", "rules": []},
    )
    assert response.status_code == 422


def test_project_counts_update(client, db, settings_row, project, subreddit):
    make_draft(db, project, subreddit)
    response = client.get(f"/api/projects/{project.id}")
    assert response.json()["draft_count"] == 1
    assert response.json()["subreddit_count"] == 1
