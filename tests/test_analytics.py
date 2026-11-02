from __future__ import annotations

from app.db import utcnow
from app.models import PublishedPost
from tests.conftest import approve_direct, make_draft

URL = "https://www.reddit.com/r/webdev/comments/metrics1/title/"


def test_manual_metrics_and_analytics(client, db, settings_row, project, subreddit):
    draft = make_draft(db, project, subreddit)
    approve_direct(db, draft)
    published = client.post(
        f"/api/drafts/{draft.id}/publish/manual/confirm", json={"url": URL}
    )
    assert published.status_code == 200
    post_id = published.json()["published_post"]["id"]

    updated = client.patch(
        f"/api/published/{post_id}/metrics",
        json={
            "upvotes": 42,
            "comments": 7,
            "views": 1000,
            "website_visits": 50,
            "referral_visits": 35,
            "notes": "Checked after 48 hours",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["upvotes"] == 42
    assert updated.json()["ctr"] == 5.0

    analytics = client.get(f"/api/analytics?project_id={project.id}")
    assert analytics.status_code == 200
    body = analytics.json()
    assert body["summary"]["total_posts"] == 1
    assert body["summary"]["total_upvotes"] == 42
    assert body["summary"]["avg_ctr"] == 5.0
    assert body["by_subreddit"][0]["subreddit"] == "webdev"
    assert body["data_source"] == "Manual entry"
    assert "does not track" in body["disclaimer"]
    assert body["weekly"][-1]["posts"] == 1

    detail = client.get(f"/api/published/{post_id}")
    assert detail.status_code == 200
    assert detail.json()["history"]
    assert detail.json()["draft"]["title"] == draft.title


def test_metrics_rejected_for_uncertain_post(client, db, settings_row, project, subreddit):
    draft = make_draft(db, project, subreddit)
    post = PublishedPost(
        draft_id=draft.id,
        project_id=project.id,
        subreddit_id=subreddit.id,
        title=draft.title,
        subreddit_name="webdev",
        status="uncertain",
        mode="api",
    )
    db.add(post)
    db.commit()
    response = client.patch(f"/api/published/{post.id}/metrics", json={"upvotes": 3})
    assert response.status_code == 409


def test_published_list_disclaimer(client, db, settings_row):
    response = client.get("/api/published")
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert "manually" in response.json()["note"]


def test_overview_empty_state_and_counts(client, db, settings_row, project, subreddit):
    overview = client.get("/api/overview")
    assert overview.status_code == 200
    empty = overview.json()
    assert empty["drafts_generated"] == 0
    assert empty["pending_approvals"] == 0
    assert empty["weekly_activity"][-1]["posts"] == 0
    assert empty["upcoming_scheduled"] == []

    make_draft(db, project, subreddit)
    filled = client.get(f"/api/overview").json()
    assert filled["drafts_generated"] == 1
    assert filled["pending_approvals"] == 1
    assert filled["ai_usage"]["generations_this_month"] == 1
    assert filled["ai_usage"]["by_model"][0]["model"] == "gemini-2.5-flash"


def test_breakdown_endpoint(client, db, settings_row, project, subreddit):
    make_draft(db, project, subreddit)
    response = client.get(f"/api/analytics/breakdown?project_id={project.id}")
    assert response.status_code == 200
    assert response.json()["draft_statuses"]["Pending Review"] == 1
