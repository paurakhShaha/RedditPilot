from __future__ import annotations

from datetime import date, timedelta
from statistics import mean

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db, utcnow
from app.models import Draft, PublishedPost, Subreddit
from app.services.serialize import serialize_published

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _week_start(value) -> date:
    return value.date() - timedelta(days=value.weekday())


@router.get("")
def analytics(db: Session = Depends(get_db), project_id: int | None = None, weeks: int = 12):
    weeks = max(4, min(52, weeks))
    query = db.query(PublishedPost).filter(PublishedPost.status == "published")
    if project_id:
        query = query.filter(PublishedPost.project_id == project_id)
    posts = query.order_by(PublishedPost.published_at.asc()).all()

    total_views = sum(post.views for post in posts)
    total_visits = sum(post.website_visits for post in posts)
    summary = {
        "total_posts": len(posts),
        "total_upvotes": sum(post.upvotes for post in posts),
        "total_comments": sum(post.comments for post in posts),
        "total_views": total_views,
        "total_website_visits": total_visits,
        "total_referral_visits": sum(post.referral_visits for post in posts),
        "avg_upvotes": round(mean([p.upvotes for p in posts]), 1) if posts else 0,
        "avg_comments": round(mean([p.comments for p in posts]), 1) if posts else 0,
        "avg_ctr": round(total_visits / total_views * 100, 2) if total_views else None,
        "manual_mode_posts": sum(1 for post in posts if post.mode == "manual"),
        "api_mode_posts": sum(1 for post in posts if post.mode == "api"),
    }

    current_week = _week_start(utcnow())
    week_starts = [current_week - timedelta(weeks=offset) for offset in range(weeks - 1, -1, -1)]
    buckets = {
        week: {"week_start": week.isoformat(), "posts": 0, "upvotes": 0, "comments": 0, "views": 0, "website_visits": 0, "referral_visits": 0}
        for week in week_starts
    }
    for post in posts:
        week = _week_start(post.published_at)
        if week in buckets:
            bucket = buckets[week]
            bucket["posts"] += 1
            bucket["upvotes"] += post.upvotes
            bucket["comments"] += post.comments
            bucket["views"] += post.views
            bucket["website_visits"] += post.website_visits
            bucket["referral_visits"] += post.referral_visits

    by_subreddit: dict[str, dict] = {}
    for post in posts:
        row = by_subreddit.setdefault(
            post.subreddit_name,
            {
                "subreddit": post.subreddit_name,
                "posts": 0,
                "upvotes": 0,
                "comments": 0,
                "views": 0,
                "website_visits": 0,
                "referral_visits": 0,
            },
        )
        row["posts"] += 1
        row["upvotes"] += post.upvotes
        row["comments"] += post.comments
        row["views"] += post.views
        row["website_visits"] += post.website_visits
        row["referral_visits"] += post.referral_visits

    recent = query.order_by(PublishedPost.published_at.desc()).limit(8).all()

    return {
        "summary": summary,
        "weekly": list(buckets.values()),
        "engagement_over_time": [
            {"week_start": row["week_start"], "upvotes": row["upvotes"], "comments": row["comments"]}
            for row in buckets.values()
        ],
        "by_subreddit": sorted(by_subreddit.values(), key=lambda row: row["upvotes"], reverse=True),
        "referral_traffic": [
            {"week_start": row["week_start"], "website_visits": row["website_visits"], "referral_visits": row["referral_visits"]}
            for row in buckets.values()
        ],
        "recent_posts": [serialize_published(post) for post in recent],
        "data_source": "Manual entry",
        "disclaimer": (
            "Upvotes, comments and views are entered by you after checking Reddit. "
            "Website visits and referral traffic are optional manual entries. "
            "RedditPilot does not track Reddit metrics automatically or claim access to analytics you have not connected."
        ),
    }


@router.get("/breakdown")
def breakdown(db: Session = Depends(get_db), project_id: int | None = None):
    """Small distribution used in the overview and analytics drawers."""
    query = db.query(PublishedPost)
    if project_id:
        query = query.filter(PublishedPost.project_id == project_id)
    posts = query.all()
    drafts = db.query(Draft)
    if project_id:
        drafts = drafts.filter(Draft.project_id == project_id)
    return {
        "draft_statuses": {
            status: drafts.filter(Draft.status == status).count()
            for status in ["Pending Review", "Approved", "Rejected", "Scheduled", "Published", "Failed", "Archived"]
        },
        "modes": {
            "manual": sum(1 for post in posts if post.mode == "manual"),
            "api": sum(1 for post in posts if post.mode == "api"),
        },
    }
