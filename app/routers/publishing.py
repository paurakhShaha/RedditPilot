from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import APIConnection
from app.schemas import ApiPublishRequest, ManualPublishConfirm
from app.services.compliance import api_publish_blockers, evaluate_draft
from app.services.publishing import (
    api_publish,
    confirm_manual_publication,
    manual_prepare,
    verify_reddit_connection,
)
from app.services.serialize import (
    get_draft,
    get_settings_row,
    iso,
    serialize_draft,
    serialize_published,
)
from app.services.settings_service import get_reddit_credentials

router = APIRouter(prefix="/api", tags=["publishing"])


def _detail(db: Session, draft) -> dict:
    payload = serialize_draft(draft)
    payload["compliance"] = evaluate_draft(db, draft, stage="publish")
    return payload


@router.get("/drafts/{draft_id}/publish/check")
def publish_check(draft_id: int, db: Session = Depends(get_db)):
    draft = get_draft(db, draft_id)
    report = evaluate_draft(db, draft, stage="publish")
    settings_row = get_settings_row(db)
    blockers = api_publish_blockers(db, draft)
    return {
        "draft_id": draft.id,
        "is_approved": draft.is_approved,
        "status": draft.status,
        "compliance": report,
        "api_eligible": settings_row.publishing_mode == "api"
        and settings_row.api_publishing_enabled
        and not blockers,
        "api_blockers": blockers,
        "publishing_mode": settings_row.publishing_mode,
        "api_publishing_enabled": settings_row.api_publishing_enabled,
        "has_credentials": bool(get_reddit_credentials(db)),
    }


@router.post("/drafts/{draft_id}/publish/manual/prepare")
def prepare_manual(draft_id: int, db: Session = Depends(get_db)):
    draft = get_draft(db, draft_id)
    result = manual_prepare(db, draft)
    result["draft"] = serialize_draft(draft)
    return result


@router.post("/drafts/{draft_id}/publish/manual/confirm")
def confirm_manual(draft_id: int, payload: ManualPublishConfirm, db: Session = Depends(get_db)):
    draft = get_draft(db, draft_id)
    post = confirm_manual_publication(
        db,
        draft,
        url=payload.url,
        note=payload.note,
        published_at=payload.published_at,
    )
    db.refresh(draft)
    return {
        "ok": True,
        "message": "Publication recorded. Metrics can be updated in Analytics.",
        "published_post": serialize_published(post),
        "draft": _detail(db, draft),
    }


@router.post("/drafts/{draft_id}/publish/api")
def publish_with_api(draft_id: int, payload: ApiPublishRequest, db: Session = Depends(get_db)):
    draft = get_draft(db, draft_id)
    result = api_publish(db, draft, note=payload.note)
    db.refresh(draft)
    return {
        "ok": True,
        "message": result["message"],
        "warning": result["warning"],
        "published_post": serialize_published(result["published_post"]),
        "draft": _detail(db, draft),
    }


@router.get("/reddit/status")
def reddit_status(db: Session = Depends(get_db)):
    connection = db.query(APIConnection).filter(APIConnection.provider == "reddit").first()
    settings_row = get_settings_row(db)
    return {
        "credentials_configured": bool(get_reddit_credentials(db)),
        "status": connection.status if connection else "disconnected",
        "username": connection.username if connection else None,
        "last_verified_at": iso(connection.last_verified_at) if connection else None,
        "last_error": connection.last_error if connection else "",
        "api_publishing_enabled": settings_row.api_publishing_enabled,
        "publishing_mode": settings_row.publishing_mode,
    }


@router.post("/reddit/verify")
def verify_reddit(db: Session = Depends(get_db)):
    result = verify_reddit_connection(db, None)
    return {"ok": True, **result}
