from __future__ import annotations

from datetime import timedelta
from statistics import mean

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db, utcnow
from app.models import AnalyticsRecord, Draft, PublishedPost
from app.schemas import MetricsUpdate, ResolvePublishRequest
from app.services.activity import log_activity
from app.services.serialize import iso, serialize_published

router = APIRouter(prefix="/api/published", tags=["published"])


@router.get("")
def list_published(db: Session = Depends(get_db), project_id: int | None = None):
    query = db.query(PublishedPost).order_by(PublishedPost.published_at.desc())
    if project_id:
        query = query.filter(PublishedPost.project_id == project_id)
    items = [serialize_published(post) for post in query.all()]
    return {
        "items": items,
        "total": len(items),
        "note": "Reddit metrics are entered manually. RedditPilot does not scrape or claim automatic tracking.",
    }


@router.get("/{post_id}")
def get_published(post_id: int, db: Session = Depends(get_db)):
    post = db.get(PublishedPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Published post not found.")
    payload = serialize_published(post)
    payload["history"] = [
        {
            "id": record.id,
            "recorded_at": iso(record.recorded_at),
            "upvotes": record.upvotes,
            "comments": record.comments,
            "views": record.views,
            "website_visits": record.website_visits,
            "referral_visits": record.referral_visits,
            "note": record.note,
        }
        for record in post.metric_history
    ]
    payload["draft"] = {
        "id": post.draft.id,
        "title": post.draft.title,
        "body": post.draft.body,
        "link_url": post.draft.link_url,
        "status": post.draft.status,
    }
    return payload


@router.patch("/{post_id}/metrics")
def update_metrics(post_id: int, payload: MetricsUpdate, db: Session = Depends(get_db)):
    post = db.get(PublishedPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Published post not found.")
    if post.status != "published":
        raise HTTPException(status_code=409, detail="Resolve the uncertain submission before adding metrics.")
    data = payload.model_dump(exclude_unset=True)
    note = data.pop("notes", None)
    if note is not None:
        post.notes = note
    for key, value in data.items():
        if value is not None:
            setattr(post, key, value)
    post.metrics_updated_at = utcnow()
    db.add(
        AnalyticsRecord(
            published_post_id=post.id,
            upvotes=post.upvotes,
            comments=post.comments,
            views=post.views,
            website_visits=post.website_visits,
            referral_visits=post.referral_visits,
            note=note or "Manual metric update",
        )
    )
    db.commit()
    db.refresh(post)
    log_activity(
        db,
        "analytics.metrics_updated",
        f"Updated manual metrics for post #{post.id}",
        entity_type="published_post",
        entity_id=post.id,
    )
    return serialize_published(post)


@router.post("/{post_id}/resolve")
def resolve_uncertain(
    post_id: int, payload: ResolvePublishRequest, db: Session = Depends(get_db)
):
    post = db.get(PublishedPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Published post not found.")
    if post.status != "uncertain":
        raise HTTPException(status_code=409, detail="Only uncertain submissions need resolution.")
    draft = db.get(Draft, post.draft_id)
    if payload.outcome == "published":
        if not payload.url:
            raise HTTPException(status_code=422, detail="A Reddit URL is required.")
        post.url = payload.url
        post.status = "published"
        post.published_at = utcnow()
        post.notes = payload.note or post.notes
        draft.status = "Published"
        if draft.scheduled_slot:
            draft.scheduled_slot.status = "published"
            draft.scheduled_slot.error = ""
        message = "Publication confirmed and recorded."
    else:
        post_url = post.url
        db.delete(post)
        draft.status = "Approved"
        draft.last_error = payload.note or "API submission confirmed as not published by the user."
        if draft.scheduled_slot:
            draft.scheduled_slot.status = "approved"
            draft.scheduled_slot.error = ""
        message = "Marked as not published. The approval is still valid; review before retrying."
        log_activity(
            db,
            "reddit.submission_resolved",
            f"Confirmed uncertain submission for draft #{draft.id} was not published ({post_url or 'no URL'})",
            entity_type="draft",
            entity_id=draft.id,
            level="warning",
            commit=False,
        )
    db.commit()
    log_activity(
        db,
        "published.resolved",
        f"Resolved uncertain publication #{post_id}: {payload.outcome}",
        entity_type="published_post",
        entity_id=post_id,
    )
    return {
        "ok": True,
        "message": message,
        "draft_status": draft.status,
        "published_post": serialize_published(post) if payload.outcome == "published" else None,
    }
