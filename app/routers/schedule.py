from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.enums import ScheduleStatus
from app.models import SchedulePlan, ScheduledPost, Subreddit
from app.schemas import PauseRequest, SchedulePlanIn
from app.services.activity import log_activity
from app.services.scheduler import materialize_slots, retry_slot, run_tick
from app.services.serialize import (
    get_project,
    get_settings_row,
    get_subreddit,
    iso,
    serialize_draft,
)
from app.services.settings_service import get_reddit_credentials, serialize_settings

router = APIRouter(prefix="/api/schedule", tags=["scheduling"])


def serialize_slot(db: Session, slot: ScheduledPost) -> dict:
    draft = slot.draft
    return {
        "id": slot.id,
        "project_id": slot.project_id,
        "project_name": slot.project.name if slot.project else "",
        "subreddit_id": slot.subreddit_id,
        "subreddit_name": slot.subreddit.name if slot.subreddit else "",
        "slot_start": iso(slot.slot_start),
        "status": slot.status,
        "objective": slot.objective,
        "post_type": slot.post_type,
        "topic_hint": slot.topic_hint,
        "draft_id": slot.draft_id,
        "draft_title": draft.title if draft else None,
        "draft_status": draft.status if draft else None,
        "error": slot.error,
        "created_at": iso(slot.created_at),
        "updated_at": iso(slot.updated_at),
    }


def _plan_payload(plan: SchedulePlan | None, project_id: int) -> dict:
    if not plan:
        return {
            "project_id": project_id,
            "configured": False,
            "subreddit_id": None,
            "objective": "Share a development story",
            "post_type": "Text post",
            "topic_hint": "",
            "enabled": False,
        }
    return {
        "id": plan.id,
        "project_id": plan.project_id,
        "configured": True,
        "subreddit_id": plan.subreddit_id,
        "subreddit_name": plan.subreddit.name if plan.subreddit else "",
        "objective": plan.objective,
        "post_type": plan.post_type,
        "topic_hint": plan.topic_hint,
        "enabled": plan.enabled,
    }


@router.get("")
def list_schedule(
    project_id: int | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(ScheduledPost)
    if project_id:
        query = query.filter(ScheduledPost.project_id == project_id)
    slots = query.order_by(ScheduledPost.slot_start.asc()).limit(limit).all()
    settings_row = get_settings_row(db)
    return {
        "items": [serialize_slot(db, slot) for slot in slots],
        "settings": serialize_settings(db),
        "warning": "The scheduler creates drafts for review. It never publishes automatically.",
    }


@router.get("/plan/{project_id}")
def get_plan(project_id: int, db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    plan = db.query(SchedulePlan).filter(SchedulePlan.project_id == project_id).first()
    settings_row = get_settings_row(db)
    return {
        "plan": _plan_payload(plan, project_id),
        "schedule": {
            "weekly_frequency": settings_row.weekly_frequency,
            "publishing_day": settings_row.publishing_day,
            "publishing_time": settings_row.publishing_time,
            "timezone": settings_row.timezone,
            "paused": settings_row.scheduling_paused,
        },
        "settings": serialize_settings(db),
    }


@router.put("/plan/{project_id}")
def save_plan(project_id: int, payload: SchedulePlanIn, db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    subreddit = get_subreddit(db, payload.subreddit_id)
    if subreddit.project_id != project_id:
        raise HTTPException(status_code=422, detail="Subreddit does not belong to this project.")
    if subreddit.approval_status in ("prohibited", "not_recommended"):
        raise HTTPException(
            status_code=409,
            detail="This community is marked as prohibited or not recommended. Choose another community.",
        )
    if subreddit.self_promotion_policy == "prohibited":
        raise HTTPException(
            status_code=409,
            detail="This community prohibits promotional content. Weekly scheduled content cannot target it.",
        )
    plan = db.query(SchedulePlan).filter(SchedulePlan.project_id == project_id).first()
    if plan is None:
        plan = SchedulePlan(project_id=project_id)
        db.add(plan)
    plan.subreddit_id = payload.subreddit_id
    plan.objective = payload.objective
    plan.post_type = payload.post_type
    plan.topic_hint = payload.topic_hint
    plan.enabled = payload.enabled
    db.commit()
    db.refresh(plan)
    materialize_slots(db)
    log_activity(
        db,
        "schedule.plan_saved",
        f"Weekly plan for '{project.name}' targeting r/{subreddit.name} ({'enabled' if plan.enabled else 'disabled'})",
        entity_type="project",
        entity_id=project_id,
    )
    return {"ok": True, "plan": _plan_payload(plan, project_id)}


@router.post("/pause")
def pause_schedule(payload: PauseRequest, db: Session = Depends(get_db)):
    settings_row = get_settings_row(db)
    settings_row.scheduling_paused = payload.paused
    db.commit()
    log_activity(
        db,
        "schedule.paused" if payload.paused else "schedule.resumed",
        "Weekly scheduling paused" if payload.paused else "Weekly scheduling resumed",
        level="warning" if payload.paused else "info",
    )
    return {"ok": True, "paused": settings_row.scheduling_paused}


@router.post("/tick")
def trigger_tick(db: Session = Depends(get_db)):
    # Manual trigger for the persistent scheduler. It creates drafts for review;
    # it cannot approve or publish anything.
    result = run_tick(db)
    return result


@router.post("/slots/{slot_id}/skip")
def skip_slot(slot_id: int, db: Session = Depends(get_db)):
    slot = db.get(ScheduledPost, slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="Scheduled slot not found.")
    if slot.status == ScheduleStatus.PUBLISHED.value:
        raise HTTPException(status_code=409, detail="Published slots cannot be skipped.")
    slot.status = ScheduleStatus.SKIPPED.value
    slot.error = "Skipped by user."
    db.commit()
    log_activity(
        db,
        "schedule.slot_skipped",
        f"Skipped scheduled slot on {iso(slot.slot_start)}",
        entity_type="scheduled_post",
        entity_id=slot.id,
    )
    return serialize_slot(db, slot)


@router.post("/slots/{slot_id}/retry")
def retry_scheduled_slot(slot_id: int, db: Session = Depends(get_db)):
    try:
        result = retry_slot(db, slot_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not result.get("ok"):
        raise HTTPException(
            status_code=502,
            detail=result.get("error") or "Draft generation failed. Check the Gemini configuration.",
        )
    return result


@router.get("/upcoming")
def upcoming(project_id: int | None = Query(default=None), db: Session = Depends(get_db)):
    from app.db import utcnow

    query = (
        db.query(ScheduledPost)
        .filter(
            ScheduledPost.slot_start >= utcnow(),
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
        .limit(12)
    )
    if project_id:
        query = query.filter(ScheduledPost.project_id == project_id)
    return {"items": [serialize_slot(db, slot) for slot in query.all()]}
