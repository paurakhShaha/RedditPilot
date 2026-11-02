from __future__ import annotations

from datetime import timedelta

from app.db import utcnow
from app.models import PublishedPost, UserSettings
from app.services.compliance import evaluate_draft
from tests.conftest import approve_direct, make_draft


def codes(report):
    return {issue["code"] for issue in report["issues"]}


def test_clean_draft_has_no_blockers(db, settings_row, project, subreddit):
    draft = make_draft(db, project, subreddit)
    report = evaluate_draft(db, draft, stage="review")
    assert report["blockers"] == 0
    assert report["level"] in ("ok", "warning")


def test_missing_disclosure_blocks_promotional_draft(db, settings_row, project, subreddit):
    draft = make_draft(
        db,
        project,
        subreddit,
        link_url="https://timetravelerreceipt.app/",
        disclosure="",
        objective="Present a project launch",
        promotional_intensity=4,
    )
    report = evaluate_draft(db, draft, stage="review")
    assert "missing_disclosure" in codes(report)
    assert report["blockers"] >= 1


def test_prohibited_promotion_blocks(db, settings_row, project, subreddit):
    subreddit.self_promotion_policy = "prohibited"
    db.commit()
    draft = make_draft(
        db,
        project,
        subreddit,
        link_url="https://timetravelerreceipt.app/",
        objective="Introduce a new project",
        promotional_intensity=3,
    )
    report = evaluate_draft(db, draft, stage="review")
    assert "promotion_prohibited" in codes(report)


def test_restricted_claims_block(db, settings_row, project, subreddit):
    draft = make_draft(
        db,
        project,
        subreddit,
        body=(
            "This project is a tool for history fans. No financial advice is intended here, and you should "
            "always do your own research before making any decision. I built it as a small side project "
            "to explore historical grocery prices with a bit of curiosity and care."
        ),
    )
    report = evaluate_draft(db, draft, stage="review")
    assert "restricted_claim" in codes(report)


def test_stale_rules_are_warning_then_publish_blocker(db, settings_row, project, subreddit):
    subreddit.last_rules_verified_at = utcnow() - timedelta(days=200)
    db.commit()
    draft = make_draft(db, project, subreddit)
    approve_direct(db, draft)
    review = evaluate_draft(db, draft, stage="review")
    publish = evaluate_draft(db, draft, stage="publish")
    assert "rules_stale" in codes(review)
    assert "rules_stale" in codes(publish)
    stale = [i for i in review["issues"] if i["code"] == "rules_stale"][0]
    stale_publish = [i for i in publish["issues"] if i["code"] == "rules_stale"][0]
    assert stale["severity"] == "warning"
    assert stale_publish["severity"] == "blocker"


def test_duplicate_title_and_body_detected(db, settings_row, project, subreddit):
    first = make_draft(db, project, subreddit)
    second = make_draft(db, project, subreddit)
    report = evaluate_draft(db, second, stage="review")
    assert "duplicate_title" in codes(report)
    assert "similar_body" in codes(report)
    assert report["duplicates"]["exact_title"][0]["draft_id"] == first.id


def test_allowed_post_type_mismatch_blocks_publish(db, settings_row, project, subreddit):
    subreddit.allowed_post_types = ["Discussion"]
    db.commit()
    draft = make_draft(db, project, subreddit, post_type="Text post")
    approve_direct(db, draft)
    report = evaluate_draft(db, draft, stage="publish")
    assert "post_type_not_allowed" in codes(report)


def test_weekly_limit_blocks_publish(db, settings_row, project, subreddit):
    first = make_draft(db, project, subreddit, title="First distinct post")
    approve_direct(db, first)
    first.status = "Published"
    db.add(
        PublishedPost(
            draft_id=first.id,
            project_id=project.id,
            subreddit_id=subreddit.id,
            url="https://www.reddit.com/r/webdev/comments/first/",
            title=first.title,
            subreddit_name="webdev",
            published_at=utcnow(),
            mode="manual",
        )
    )
    second = make_draft(db, project, subreddit, title="Second distinct post", body="Another completely different body about testing parsers in small projects. " * 4)
    approve_direct(db, second)
    report = evaluate_draft(db, second, stage="publish")
    assert "weekly_limit" in codes(report)
    assert report["weekly"]["remaining"] == 0


def test_unapproved_publish_is_blocked(db, settings_row, project, subreddit):
    draft = make_draft(db, project, subreddit)
    report = evaluate_draft(db, draft, stage="publish")
    assert "not_approved" in codes(report)


def test_weekly_frequency_three_allows_three(db, settings_row, project, subreddit):
    settings_row.weekly_frequency = 3
    db.commit()
    draft = make_draft(db, project, subreddit)
    approve_direct(db, draft)
    report = evaluate_draft(db, draft, stage="publish")
    assert report["weekly"]["limit"] == 3
    assert report["weekly"]["remaining"] == 3
