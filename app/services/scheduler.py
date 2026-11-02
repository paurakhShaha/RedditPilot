"""Database-backed weekly scheduling.

APScheduler is only a trigger. The authoritative schedule lives in
`scheduled_posts`; every tick is idempotent and can be run manually. Scheduled
slots produce drafts in the review queue and never publish anything.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import utcnow
from app.enums import DraftStatus, ScheduleStatus
from app.models import Draft, Project, SchedulePlan, ScheduledPost, Subreddit
from app.services.activity import log_activity
from app.services.gemini import GeminiError, generate_post
from app.services.serialize import iso
from app.services.settings_service import get_gemini_key, get_settings_row

logger = logging.getLogger("redditpilot.scheduler")
_tick_lock = threading.Lock()

LEAD_HOURS = 72
STALE_HOURS = 6
FREQUENCY_OFFSETS = {1: [0], 2: [0, 3], 3: [0, 2, 4]}


def _slot_datetimes_utc(settings_row, plan: SchedulePlan, now_utc: datetime) -> list[datetime]:
    """Slots for the current week and the next four weeks, in the user's timezone."""
    tz = ZoneInfo(settings_row.timezone)
    local_now = now_utc.replace(tzinfo=timezone.utc).astimezone(tz)
    hour, minute = (int(part) for part in settings_row.publishing_time.split(":"))
    week_start = (local_now - timedelta(days=local_now.weekday())).date()
    offsets = FREQUENCY_OFFSETS.get(settings_row.weekly_frequency, [0])
    slots: list[datetime] = []
    for week in range(0, 5):
        monday = week_start + timedelta(days=7 * week)
        for offset in offsets:
            # Slots stay inside the selected week even when frequency > 1.
            days_from_monday = (settings_row.publishing_day + offset) % 7
            local_day = monday + timedelta(days=days_from_monday)
            local_slot = datetime.combine(local_day, time(hour, minute), tzinfo=tz)
            slot_utc = local_slot.astimezone(timezone.utc).replace(tzinfo=None)
            if slot_utc <= now_utc - timedelta(hours=STALE_HOURS):
                continue
            slots.append(slot_utc)
    return slots


def materialize_slots(db: Session, now_utc: datetime | None = None) -> int:
    now_utc = now_utc or utcnow()
    settings_row = get_settings_row(db)
    if settings_row.scheduling_paused:
        return 0
    plans = (
        db.query(SchedulePlan)
        .join(Project, SchedulePlan.project_id == Project.id)
        .filter(
            SchedulePlan.enabled.is_(True),
            Project.is_archived.is_(False),
        )
        .all()
    )
    created = 0
    for plan in plans:
        subreddit = db.get(Subreddit, plan.subreddit_id)
        if not subreddit or subreddit.project_id != plan.project_id:
            continue
        for slot_utc in _slot_datetimes_utc(settings_row, plan, now_utc):
            exists = (
                db.query(ScheduledPost)
                .filter(
                    ScheduledPost.project_id == plan.project_id,
                    ScheduledPost.slot_start == slot_utc,
                )
                .first()
            )
            if exists:
                continue
            db.add(
                ScheduledPost(
                    project_id=plan.project_id,
                    subreddit_id=plan.subreddit_id,
                    slot_start=slot_utc,
                    status=ScheduleStatus.PLANNED.value,
                    objective=plan.objective,
                    post_type=plan.post_type,
                    topic_hint=plan.topic_hint,
                )
            )
            try:
                db.commit()
                created += 1
            except IntegrityError:
                db.rollback()
    return created


def next_slot_preview(db: Session, project_id: int) -> str | None:
    slot = (
        db.query(ScheduledPost)
        .filter(
            ScheduledPost.project_id == project_id,
            ScheduledPost.slot_start >= utcnow(),
            ScheduledPost.status.notin_(
                [ScheduleStatus.SKIPPED.value, ScheduleStatus.FAILED.value]
            ),
        )
        .order_by(ScheduledPost.slot_start.asc())
        .first()
    )
    return iso(slot.slot_start) if slot else None


def _generate_for_slot(db: Session, slot: ScheduledPost, settings_row) -> Draft | None:
    from app.services.draft_service import create_generated_draft

    if slot.draft_id:
        return db.get(Draft, slot.draft_id)
    project = db.get(Project, slot.project_id)
    subreddit = db.get(Subreddit, slot.subreddit_id)
    if not project or not subreddit:
        slot.status = ScheduleStatus.FAILED.value
        slot.error = "Project or subreddit no longer exists."
        db.commit()
        return None

    api_key = get_gemini_key(db)
    if not api_key:
        slot.status = ScheduleStatus.FAILED.value
        slot.error = "No Gemini API key configured. Add one in Settings, then retry this slot."
        db.commit()
        log_activity(
            db,
            "schedule.generation_failed",
            f"Weekly slot {iso(slot.slot_start)} could not generate a draft: Gemini key missing.",
            entity_type="scheduled_post",
            entity_id=slot.id,
            level="warning",
        )
        return None

    recent_titles = [
        row[0]
        for row in db.query(Draft.title)
        .filter(Draft.project_id == project.id)
        .order_by(Draft.created_at.desc())
        .limit(10)
        .all()
    ]
    topic = slot.topic_hint.strip() or (
        f"An honest, specific update related to {project.product_category or 'building the project'}: "
        f"{project.description[:240]}"
    )
    link_preference = "none"
    if (
        settings_row.default_include_link
        and subreddit.self_promotion_policy == "allowed_with_disclosure"
    ):
        link_preference = "optional"

    slot.status = ScheduleStatus.GENERATING.value
    slot.error = ""
    db.commit()
    try:
        generated = generate_post(
            project=project,
            subreddit=subreddit,
            objective=slot.objective,
            topic=topic,
            post_type=slot.post_type,
            link_preference=link_preference,
            additional_notes=(
                f"This is the weekly scheduled slot for {iso(slot.slot_start)}. "
                "Create a distinct angle from recent drafts."
            ),
            preferences=settings_row,
            recent_titles=recent_titles,
            api_key=api_key,
            model=settings_row.gemini_model,
        )
        draft = create_generated_draft(
            db,
            project=project,
            subreddit=subreddit,
            generated=generated,
            objective=slot.objective,
            topic=topic,
            post_type=slot.post_type,
            model=settings_row.gemini_model,
            source="scheduled",
            commit=False,
        )
        slot.draft_id = draft.id
        slot.status = ScheduleStatus.DRAFT_READY.value
        slot.error = ""
        db.commit()
        db.refresh(draft)
        log_activity(
            db,
            "schedule.draft_ready",
            f"Scheduled slot {iso(slot.slot_start)} has draft #{draft.id} awaiting review.",
            entity_type="scheduled_post",
            entity_id=slot.id,
        )
        return draft
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        # Re-read the slot after rollback before updating it.
        slot = db.get(ScheduledPost, slot.id)
        if slot:
            slot.status = ScheduleStatus.FAILED.value
            slot.error = str(exc)[:1000] if isinstance(exc, (GeminiError,)) else (
                "Draft generation failed. Check Settings and retry this slot."
            )
            db.commit()
        logger.exception("Scheduled generation failed for slot %s", slot.id if slot else "?")
        log_activity(
            db,
            "schedule.generation_failed",
            f"Scheduled slot {iso(slot.slot_start) if slot else ''}: generation failed.",
            entity_type="scheduled_post",
            entity_id=slot.id if slot else None,
            level="error",
        )
        return None


def run_tick(db: Session, now_utc: datetime | None = None, *, generate: bool = True) -> dict:
    """Run one idempotent scheduling tick.

    - Materialises future slots.
    - Generates a draft for slots within the 72-hour lead window.
    - Marks slots that are too old as skipped.
    - Never publishes.
    """
    now_utc = now_utc or utcnow()
    if not _tick_lock.acquire(blocking=False):
        return {"ok": True, "skipped": "Another scheduling tick is running."}
    try:
        settings_row = get_settings_row(db)
        if settings_row.scheduling_paused:
            return {"ok": True, "paused": True, "materialized": 0, "generated": 0}

        materialized = materialize_slots(db, now_utc)
        generated = 0
        failed = 0
        skipped = 0

        stale = (
            db.query(ScheduledPost)
            .filter(
                ScheduledPost.status.in_(
                    [ScheduleStatus.PLANNED.value, ScheduleStatus.GENERATING.value]
                ),
                ScheduledPost.slot_start < now_utc - timedelta(hours=STALE_HOURS),
                ScheduledPost.draft_id.is_(None),
            )
            .all()
        )
        for slot in stale:
            slot.status = ScheduleStatus.SKIPPED.value
            slot.error = "Slot passed before a draft was generated."
            skipped += 1
        db.commit()

        if generate:
            due = (
                db.query(ScheduledPost)
                .filter(
                    ScheduledPost.status == ScheduleStatus.PLANNED.value,
                    ScheduledPost.draft_id.is_(None),
                    ScheduledPost.slot_start >= now_utc - timedelta(hours=STALE_HOURS),
                    ScheduledPost.slot_start <= now_utc + timedelta(hours=LEAD_HOURS),
                )
                .order_by(ScheduledPost.slot_start.asc())
                .all()
            )
            for slot in due:
                # Do not generate for paused scheduling even if paused during the loop.
                if get_settings_row(db).scheduling_paused:
                    break
                plan = db.query(SchedulePlan).filter(SchedulePlan.project_id == slot.project_id).first()
                if not plan or not plan.enabled:
                    continue
                before = slot.status
                draft = _generate_for_slot(db, slot, settings_row)
                db.refresh(slot)
                if draft:
                    generated += 1
                elif slot.status == ScheduleStatus.FAILED.value and before != ScheduleStatus.FAILED.value:
                    failed += 1

        return {
            "ok": True,
            "paused": False,
            "materialized": materialized,
            "generated": generated,
            "failed": failed,
            "skipped": skipped,
            "ran_at": iso(now_utc),
        }
    finally:
        _tick_lock.release()


def retry_slot(db: Session, slot_id: int) -> dict:
    settings_row = get_settings_row(db)
    if settings_row.scheduling_paused:
        raise ValueError("Scheduling is paused. Resume it before retrying a slot.")
    slot = db.get(ScheduledPost, slot_id)
    if not slot:
        raise ValueError("Scheduled slot not found.")
    if slot.draft_id:
        raise ValueError("This slot already has a draft. Open it in the Draft Queue.")
    if slot.status == ScheduleStatus.PUBLISHED.value:
        raise ValueError("This slot is already published.")
    plan = db.query(SchedulePlan).filter(SchedulePlan.project_id == slot.project_id).first()
    if not plan or not plan.enabled:
        raise ValueError("The project schedule plan is disabled.")
    slot.status = ScheduleStatus.PLANNED.value
    slot.error = ""
    db.commit()
    draft = _generate_for_slot(db, slot, settings_row)
    db.refresh(slot)
    return {
        "ok": draft is not None,
        "draft_id": draft.id if draft else None,
        "status": slot.status,
        "error": slot.error,
    }
