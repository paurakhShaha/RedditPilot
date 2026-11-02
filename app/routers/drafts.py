from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.enums import DraftStatus
from app.models import Draft
from app.schemas import (
    ApprovalRequest,
    DraftGenerateRequest,
    DraftUpdate,
    DuplicateRequest,
    RejectRequest,
)
from app.services.activity import log_activity
from app.services.compliance import evaluate_draft, refresh_compliance
from app.services.draft_service import (
    apply_regeneration,
    approve_draft,
    archive_draft,
    create_generated_draft,
    delete_draft,
    reject_draft,
    update_draft,
)
from app.services.gemini import (
    GeminiError,
    GeminiPolicyError,
    generate_post,
)
from app.services.serialize import (
    get_draft,
    get_project,
    get_settings_row,
    get_subreddit,
    serialize_draft,
    serialize_published,
)
from app.services.settings_service import get_gemini_key

router = APIRouter(prefix="/api/drafts", tags=["drafts"])


def _validate_community(db: Session, project_id: int, subreddit_id: int):
    project = get_project(db, project_id)
    subreddit = get_subreddit(db, subreddit_id)
    if subreddit.project_id != project_id:
        raise HTTPException(status_code=422, detail="The selected subreddit does not belong to this project.")
    return project, subreddit


def _guard_community(subreddit) -> None:
    if subreddit.approval_status == "prohibited":
        raise HTTPException(
            status_code=409,
            detail=f"You marked r/{subreddit.name} as prohibiting promotional content. Change its status in Subreddit Manager if that assessment is outdated.",
        )
    if subreddit.approval_status == "not_recommended":
        raise HTTPException(
            status_code=409,
            detail=f"You marked r/{subreddit.name} as not recommended. Review its rules and update the status first.",
        )


def _recent_titles(db: Session, project_id: int, exclude_id: int | None = None) -> list[str]:
    query = db.query(Draft.title).filter(Draft.project_id == project_id)
    if exclude_id:
        query = query.filter(Draft.id != exclude_id)
    return [row[0] for row in query.order_by(Draft.created_at.desc()).limit(12).all()]


def _detail(db: Session, draft: Draft) -> dict:
    payload = serialize_draft(draft)
    payload["approved_revisions"] = [
        {
            "id": revision.id,
            "version": revision.version,
            "title": revision.title,
            "body": revision.body,
            "disclosure": revision.disclosure,
            "link_url": revision.link_url,
            "change_note": revision.change_note,
            "created_at": revision.created_at.isoformat() + "Z",
        }
        for revision in draft.revisions
    ]
    payload["approval_history"] = [
        {
            "id": approval.id,
            "approved_at": approval.approved_at.isoformat() + "Z",
            "approved_by": approval.approved_by,
            "note": approval.note,
            "is_valid": approval.is_valid,
            "invalidated_at": approval.invalidated_at.isoformat() + "Z"
            if approval.invalidated_at
            else None,
            "invalidation_reason": approval.invalidation_reason,
        }
        for approval in draft.approvals
    ]
    return payload


@router.get("")
def list_drafts(
    status: str | None = Query(default=None),
    project_id: int | None = Query(default=None),
    subreddit_id: int | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(Draft)
    if status and status != "all":
        if status not in {item.value for item in DraftStatus}:
            raise HTTPException(status_code=422, detail="Unknown draft status filter.")
        query = query.filter(Draft.status == status)
    if project_id:
        query = query.filter(Draft.project_id == project_id)
    if subreddit_id:
        query = query.filter(Draft.subreddit_id == subreddit_id)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(Draft.title.ilike(term) | Draft.body.ilike(term))
    total = query.count()
    drafts = query.order_by(Draft.updated_at.desc()).limit(limit).all()
    counts = {item.value: 0 for item in DraftStatus}
    for row in db.query(Draft.status).all():
        counts[row[0]] = counts.get(row[0], 0) + 1
    return {
        "items": [_detail(db, draft) for draft in drafts],
        "total": total,
        "status_counts": counts,
    }


@router.get("/{draft_id}")
def get_draft_detail(draft_id: int, db: Session = Depends(get_db)):
    draft = get_draft(db, draft_id)
    draft.compliance_snapshot = evaluate_draft(db, draft, stage="review")
    db.commit()
    return _detail(db, draft)


@router.post("/generate", status_code=201)
def generate_draft(payload: DraftGenerateRequest, db: Session = Depends(get_db)):
    project, subreddit = _validate_community(db, payload.project_id, payload.subreddit_id)
    _guard_community(subreddit)
    settings_row = get_settings_row(db)
    api_key = get_gemini_key(db)
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="No Gemini API key is configured. Add one in Settings or set GEMINI_API_KEY in .env.",
        )
    if (
        subreddit.self_promotion_policy == "prohibited"
        and payload.link_preference != "none"
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                f"r/{subreddit.name} prohibits promotional content. A draft with a project link "
                "is blocked. Choose 'No link', or select a different community."
            ),
        )
    try:
        generated = generate_post(
            project=project,
            subreddit=subreddit,
            objective=payload.objective,
            topic=payload.topic,
            post_type=payload.post_type,
            link_preference=payload.link_preference,
            additional_notes=payload.additional_notes,
            preferences=settings_row,
            recent_titles=_recent_titles(db, project.id),
            api_key=api_key,
            model=settings_row.gemini_model,
        )
        draft = create_generated_draft(
            db,
            project=project,
            subreddit=subreddit,
            generated=generated,
            objective=payload.objective,
            topic=payload.topic,
            post_type=payload.post_type,
            model=settings_row.gemini_model,
            source="studio",
        )
    except GeminiPolicyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except GeminiError as exc:
        log_activity(db, "gemini.error", str(exc), level="error")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _detail(db, draft)


@router.patch("/{draft_id}")
def edit_draft(draft_id: int, payload: DraftUpdate, db: Session = Depends(get_db)):
    draft = get_draft(db, draft_id)
    data = payload.model_dump(exclude_unset=True)
    clear_link = "link_url" in data and data["link_url"] is None
    try:
        draft = update_draft(
            db,
            draft,
            title=data.get("title"),
            body=data.get("body"),
            disclosure=data.get("disclosure"),
            link_url=data.get("link_url") if not clear_link else None,
            clear_link=clear_link,
            change_note=data.get("change_note", "Manual edit"),
        )
    except HTTPException:
        raise
    return _detail(db, draft)


@router.post("/{draft_id}/regenerate")
def regenerate_draft(draft_id: int, db: Session = Depends(get_db)):
    draft = get_draft(db, draft_id)
    if draft.status == DraftStatus.PUBLISHED.value:
        raise HTTPException(status_code=409, detail="Published drafts cannot be regenerated.")
    _guard_community(draft.subreddit)
    settings_row = get_settings_row(db)
    api_key = get_gemini_key(db)
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="No Gemini API key is configured. Add one in Settings before regenerating.",
        )
    link_preference = "none"
    if draft.link_url and draft.subreddit.self_promotion_policy != "prohibited":
        link_preference = "optional"
    try:
        generated = generate_post(
            project=draft.project,
            subreddit=draft.subreddit,
            objective=draft.objective,
            topic=draft.topic,
            post_type=draft.post_type,
            link_preference=link_preference,
            additional_notes=(
                "This is a fresh regeneration. Find a materially different angle from the current "
                "draft and previous attempts; do not paraphrase them."
            ),
            preferences=settings_row,
            recent_titles=_recent_titles(db, draft.project_id, exclude_id=draft.id),
            api_key=api_key,
            model=settings_row.gemini_model,
        )
        draft = apply_regeneration(db, draft, generated, model=settings_row.gemini_model)
    except GeminiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _detail(db, draft)


@router.post("/{draft_id}/duplicate", status_code=201)
def duplicate_draft(draft_id: int, payload: DuplicateRequest, db: Session = Depends(get_db)):
    original = get_draft(db, draft_id)
    target = get_subreddit(db, payload.subreddit_id)
    if target.project_id != original.project_id:
        raise HTTPException(status_code=422, detail="The target subreddit must belong to the same project.")
    _guard_community(target)
    settings_row = get_settings_row(db)
    api_key = get_gemini_key(db)
    if not api_key:
        raise HTTPException(status_code=400, detail="No Gemini API key configured.")
    link_preference = "none"
    if original.link_url and target.self_promotion_policy != "prohibited" and target.links_policy != "not_allowed":
        link_preference = "optional"
    topic = payload.topic or original.topic
    try:
        generated = generate_post(
            project=original.project,
            subreddit=target,
            objective=original.objective,
            topic=topic,
            post_type=original.post_type,
            link_preference=link_preference,
            additional_notes=(
                f"{payload.additional_notes}\nCreate a fresh post for a different community. "
                f"Do not reuse the title or wording of: {original.title}"
            ).strip(),
            preferences=settings_row,
            recent_titles=_recent_titles(db, original.project_id),
            api_key=api_key,
            model=settings_row.gemini_model,
        )
        draft = create_generated_draft(
            db,
            project=original.project,
            subreddit=target,
            generated=generated,
            objective=original.objective,
            topic=topic,
            post_type=original.post_type,
            model=settings_row.gemini_model,
            source="duplicate",
            parent_draft_id=original.id,
        )
    except GeminiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _detail(db, draft)


@router.post("/{draft_id}/approve")
def approve(draft_id: int, payload: ApprovalRequest, db: Session = Depends(get_db)):
    draft = get_draft(db, draft_id)
    _guard_community(draft.subreddit)
    draft = approve_draft(db, draft, payload.note)
    draft.compliance_snapshot = evaluate_draft(db, draft, stage="review")
    db.commit()
    return _detail(db, draft)


@router.post("/{draft_id}/reject")
def reject(draft_id: int, payload: RejectRequest, db: Session = Depends(get_db)):
    draft = get_draft(db, draft_id)
    draft = reject_draft(db, draft, payload.reason)
    return _detail(db, draft)


@router.post("/{draft_id}/archive")
def archive(draft_id: int, db: Session = Depends(get_db)):
    draft = get_draft(db, draft_id)
    draft = archive_draft(db, draft)
    return _detail(db, draft)


@router.post("/{draft_id}/restore")
def restore(draft_id: int, db: Session = Depends(get_db)):
    draft = get_draft(db, draft_id)
    if draft.status != DraftStatus.ARCHIVED.value:
        raise HTTPException(status_code=409, detail="Only archived drafts can be restored.")
    draft.status = DraftStatus.PENDING_REVIEW.value
    draft.archived_at = None
    refresh_compliance(db, draft)
    db.commit()
    db.refresh(draft)
    log_activity(db, "draft.restored", f"Restored draft #{draft.id}", entity_type="draft", entity_id=draft.id)
    return _detail(db, draft)


@router.delete("/{draft_id}")
def delete(draft_id: int, db: Session = Depends(get_db)):
    draft = get_draft(db, draft_id)
    delete_draft(db, draft)
    return {"ok": True, "message": "Draft deleted."}


@router.get("/{draft_id}/compliance")
def compliance(draft_id: int, db: Session = Depends(get_db)):
    draft = get_draft(db, draft_id)
    report = evaluate_draft(db, draft, stage="review")
    draft.compliance_snapshot = report
    db.commit()
    return report
