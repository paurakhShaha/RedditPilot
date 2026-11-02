from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from app.config import BASE_DIR, settings as app_settings
from app.db import get_db, utcnow
from app.models import (
    ActivityLog,
    AnalyticsRecord,
    APIConnection,
    Approval,
    Draft,
    DraftRevision,
    Project,
    PublishedPost,
    ScheduledPost,
    Subreddit,
    SubredditRule,
)
from app.schemas import SettingsUpdate
from app.security import encrypt_secret
from app.services.activity import log_activity
from app.services.gemini import GeminiError, test_gemini_connection
from app.services.serialize import (
    get_project,
    get_settings_row,
    iso,
    serialize_project,
    serialize_subreddit,
)
from app.services.settings_service import (
    clear_reddit_credentials,
    get_gemini_key,
    save_reddit_credentials,
    serialize_settings,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def read_settings(db: Session = Depends(get_db)):
    return serialize_settings(db)


@router.patch("")
def update_settings(payload: SettingsUpdate, db: Session = Depends(get_db)):
    row = get_settings_row(db)
    data = payload.model_dump(exclude_unset=True)
    data.pop("reddit", None)
    data.pop("gemini_api_key", None)
    clear_key = data.pop("clear_gemini_key", False)
    clear_reddit = data.pop("clear_reddit_credentials", False)
    ack = data.pop("api_enable_acknowledged", False)

    if payload.default_project_id is not None:
        get_project(db, payload.default_project_id)
        row.default_project_id = payload.default_project_id

    if clear_key:
        row.gemini_api_key_enc = None
    elif payload.gemini_api_key and payload.gemini_api_key.strip():
        row.gemini_api_key_enc = encrypt_secret(payload.gemini_api_key.strip())

    if "api_publishing_enabled" in data and data["api_publishing_enabled"] is True:
        if not row.api_publishing_enabled and not ack:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Enabling API publishing requires explicit acknowledgement that you have legitimate "
                    "Reddit API access, will follow Reddit's terms and commercial-use requirements, and "
                    "will review every post before submission."
                ),
            )
        row.api_publishing_enabled = True
    elif "api_publishing_enabled" in data:
        row.api_publishing_enabled = bool(data["api_publishing_enabled"])

    allowed_fields = {
        "gemini_model",
        "weekly_frequency",
        "publishing_day",
        "publishing_time",
        "timezone",
        "scheduling_paused",
        "publishing_mode",
        "generation_temperature",
        "max_promo_score",
        "avoid_emojis",
        "default_include_link",
        "extra_generation_notes",
    }
    for key in allowed_fields:
        if key in data and data[key] is not None:
            setattr(row, key, data[key])

    if payload.reddit is not None:
        save_reddit_credentials(db, payload.reddit.model_dump())
    if clear_reddit:
        clear_reddit_credentials(db)

    db.commit()
    log_activity(db, "settings.updated", "Application settings updated")
    return serialize_settings(db)


@router.post("/test-gemini")
def test_gemini(db: Session = Depends(get_db)):
    row = get_settings_row(db)
    key = get_gemini_key(db)
    if not key:
        raise HTTPException(status_code=400, detail="No Gemini API key is configured.")
    try:
        model = test_gemini_connection(key, row.gemini_model)
    except GeminiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    log_activity(db, "gemini.verified", f"Gemini connection verified with {model}")
    return {"ok": True, "model": model, "message": f"Connected to {model}."}


@router.get("/export")
def export_data(db: Session = Depends(get_db)):
    projects = db.query(Project).all()
    subreddits = db.query(Subreddit).all()
    drafts = db.query(Draft).all()
    revisions = db.query(DraftRevision).all()
    approvals = db.query(Approval).all()
    scheduled = db.query(ScheduledPost).all()
    published = db.query(PublishedPost).all()
    analytics = db.query(AnalyticsRecord).all()
    payload = {
        "exported_at": iso(utcnow()),
        "app": "RedditPilot",
        "note": "Secrets and API credentials are excluded from this export.",
        "settings": serialize_settings(db),
        "projects": [serialize_project(db, project) for project in projects],
        "subreddits": [
            {
                **serialize_subreddit(subreddit),
                "rules": [
                    {"title": rule.title, "detail": rule.detail, "position": rule.position}
                    for rule in subreddit.rules
                ],
            }
            for subreddit in subreddits
        ],
        "drafts": [
            {
                "id": d.id,
                "project_id": d.project_id,
                "subreddit_id": d.subreddit_id,
                "title": d.title,
                "body": d.body,
                "disclosure": d.disclosure,
                "link_url": d.link_url,
                "objective": d.objective,
                "post_type": d.post_type,
                "topic": d.topic,
                "status": d.status,
                "promotional_intensity": d.promotional_intensity,
                "relevance": d.relevance,
                "warnings": d.warnings,
                "rule_violations": d.rule_violations,
                "model": d.model,
                "version": d.version,
                "content_hash": d.content_hash,
                "created_at": iso(d.created_at),
                "updated_at": iso(d.updated_at),
            }
            for d in drafts
        ],
        "revisions": [
            {
                "draft_id": r.draft_id,
                "version": r.version,
                "title": r.title,
                "body": r.body,
                "disclosure": r.disclosure,
                "link_url": r.link_url,
                "change_note": r.change_note,
                "created_at": iso(r.created_at),
            }
            for r in revisions
        ],
        "approvals": [
            {
                "draft_id": a.draft_id,
                "approved_at": iso(a.approved_at),
                "approved_by": a.approved_by,
                "note": a.note,
                "is_valid": a.is_valid,
                "invalidated_at": iso(a.invalidated_at),
                "invalidation_reason": a.invalidation_reason,
            }
            for a in approvals
        ],
        "scheduled_posts": [
            {
                "id": s.id,
                "project_id": s.project_id,
                "subreddit_id": s.subreddit_id,
                "slot_start": iso(s.slot_start),
                "status": s.status,
                "objective": s.objective,
                "post_type": s.post_type,
                "topic_hint": s.topic_hint,
                "draft_id": s.draft_id,
                "error": s.error,
            }
            for s in scheduled
        ],
        "published_posts": [
            {
                "id": p.id,
                "draft_id": p.draft_id,
                "project_id": p.project_id,
                "subreddit_id": p.subreddit_id,
                "reddit_post_id": p.reddit_post_id,
                "url": p.url,
                "title": p.title,
                "subreddit_name": p.subreddit_name,
                "published_at": iso(p.published_at),
                "mode": p.mode,
                "status": p.status,
                "upvotes": p.upvotes,
                "comments": p.comments,
                "views": p.views,
                "website_visits": p.website_visits,
                "referral_visits": p.referral_visits,
                "notes": p.notes,
            }
            for p in published
        ],
        "analytics_records": [
            {
                "published_post_id": a.published_post_id,
                "recorded_at": iso(a.recorded_at),
                "upvotes": a.upvotes,
                "comments": a.comments,
                "views": a.views,
                "website_visits": a.website_visits,
                "referral_visits": a.referral_visits,
                "note": a.note,
            }
            for a in analytics
        ],
    }
    filename = f"redditpilot-export-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    return JSONResponse(
        content=json.loads(json.dumps(payload, default=str)),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/backup")
@router.post("/backup")
def backup_database(db: Session = Depends(get_db)):
    if not app_settings.database_url.startswith("sqlite"):
        raise HTTPException(status_code=400, detail="In-app backups are only available for SQLite.")
    db_path = app_settings.database_url.replace("sqlite:///", "", 1)
    source_path = Path(db_path)
    if not source_path.is_absolute():
        source_path = BASE_DIR / source_path
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="Database file not found.")
    backups_dir = source_path.parent / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    target = backups_dir / f"redditpilot-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
    source = sqlite3.connect(str(source_path))
    dest = sqlite3.connect(str(target))
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()
    log_activity(db, "database.backup", f"Database backup created: {target.name}")
    return FileResponse(
        path=str(target),
        filename=target.name,
        media_type="application/octet-stream",
    )


@router.get("/activity")
def activity(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    rows = db.query(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(limit).all()
    return {
        "items": [
            {
                "id": row.id,
                "actor": row.actor,
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "message": row.message,
                "level": row.level,
                "created_at": iso(row.created_at),
            }
            for row in rows
        ]
    }
