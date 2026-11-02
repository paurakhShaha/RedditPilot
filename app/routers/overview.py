from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db, utcnow
from app.enums import DraftStatus, ScheduleStatus
from app.models import (
    ActivityLog,
    Draft,
    Project,
    PublishedPost,
    ScheduledPost,
    Subreddit,
)
from app.services.compliance import evaluate_draft
from app.services.serialize import iso, serialize_draft, serialize_published

router = APIRouter(prefix="/api/overview", tags=["overview"])


@router.get("")
def overview(db: Session = Depends(get_db), project_id: int | None = None):
    draft_query = db.query(Draft)
    subreddit_query = db.query(Subreddit)
    published_query = db.query(PublishedPost)
    slot_query = db.query(ScheduledPost)
    project_query = db.query(Project).filter(Project.is_archived.is_(False))
    if project_id:
        draft_query = draft_query.filter(Draft.project_id == project_id)
        subreddit_query = subreddit_query.filter(Subreddit.project_id == project_id)
        published_query = published_query.filter(PublishedPost.project_id == project_id)
        slot_query = slot_query.filter(ScheduledPost.project_id == project_id)
        project_query = project_query.filter(Project.id == project_id)

    now = utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)

    pending_drafts = draft_query.filter(Draft.status == DraftStatus.PENDING_REVIEW.value).all()
    blocking = 0
    for draft in pending_drafts:
        report = evaluate_draft(db, draft, stage="review")
        if report["blockers"]:
            blocking += 1

    published_count = published_query.filter(PublishedPost.status == "published").count()
    weekly_series = []
    for offset in range(7, -1, -1):
        start = week_start - timedelta(weeks=offset)
        end = start + timedelta(days=7)
        count = (
            published_query.filter(
                PublishedPost.status == "published",
                PublishedPost.published_at >= start,
                PublishedPost.published_at < end,
            ).count()
        )
        weekly_series.append({"week_start": start.date().isoformat(), "posts": count})

    weekly_ai = draft_query.filter(
        Draft.created_at >= month_start, Draft.model != ""
    ).count()
    by_model = [
        {"model": row[0] or "unknown", "count": row[1]}
        for row in draft_query.with_entities(Draft.model, func.count(Draft.id))
        .filter(Draft.created_at >= month_start, Draft.model != "")
        .group_by(Draft.model)
        .all()
    ]

    recent_posts = (
        published_query.order_by(PublishedPost.published_at.desc()).limit(5).all()
    )
    upcoming = (
        slot_query.filter(
            ScheduledPost.slot_start >= now,
            ScheduledPost.status.in_(
                [
                    ScheduleStatus.PLANNED.value,
                    ScheduleStatus.GENERATING.value,
                    ScheduleStatus.DRAFT_READY.value,
                    ScheduleStatus.APPROVED.value,
                ]
            ),
        )
        .order_by(ScheduledPost.slot_start.asc())
        .limit(5)
        .all()
    )
    activity = (
        db.query(ActivityLog)
        .order_by(ActivityLog.created_at.desc())
        .limit(8)
        .all()
    )
    from app.services.serialize import serialize_subreddit

    return {
        "project_count": project_query.count(),
        "subreddit_count": subreddit_query.count(),
        "drafts_generated": draft_query.count(),
        "pending_approvals": draft_query.filter(
            Draft.status == DraftStatus.PENDING_REVIEW.value
        ).count(),
        "pending_with_blockers": blocking,
        "approved_drafts": draft_query.filter(
            Draft.status.in_([DraftStatus.APPROVED.value, DraftStatus.SCHEDULED.value])
        ).count(),
        "published_posts": published_count,
        "scheduled_posts": slot_query.filter(
            ScheduledPost.slot_start >= now,
            ScheduledPost.status.in_(
                [
                    ScheduleStatus.PLANNED.value,
                    ScheduleStatus.GENERATING.value,
                    ScheduleStatus.DRAFT_READY.value,
                    ScheduleStatus.APPROVED.value,
                ]
            ),
        ).count(),
        "weekly_activity": weekly_series,
        "recent_published": [serialize_published(post) for post in recent_posts],
        "upcoming_scheduled": [
            {
                "id": slot.id,
                "slot_start": iso(slot.slot_start),
                "subreddit_name": slot.subreddit.name if slot.subreddit else "",
                "project_name": slot.project.name if slot.project else "",
                "status": slot.status,
                "draft_id": slot.draft_id,
                "draft_title": slot.draft.title if slot.draft else None,
                "draft_status": slot.draft.status if slot.draft else None,
            }
            for slot in upcoming
        ],
        "ai_usage": {
            "generations_this_month": weekly_ai,
            "by_model": by_model,
            "note": "Counts AI-generated drafts saved this month. Token usage is not exposed by the local app.",
        },
        "recent_activity": [
            {
                "id": entry.id,
                "action": entry.action,
                "message": entry.message,
                "level": entry.level,
                "created_at": iso(entry.created_at),
            }
            for entry in activity
        ],
        "rules_unverified": subreddit_query.filter(
            Subreddit.last_rules_verified_at.is_(None)
        ).count(),
        "compliance_note": (
            "One post per week is a personal pacing rule, not a guarantee of Reddit compliance. "
            "Always check each community's current rules."
        ),
    }
