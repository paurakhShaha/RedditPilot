"""Draft lifecycle: persistence, edit history, approval and rejection."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db import utcnow
from app.enums import DraftStatus, ScheduleStatus
from app.models import Approval, Draft, DraftRevision, Project, Subreddit
from app.services.activity import log_activity
from app.services.compliance import (
    evaluate_draft,
    is_promotional,
    refresh_compliance,
)
from app.services.gemini import GeneratedPost
from app.services.serialize import content_hash
from app.services.settings_service import get_settings_row

logger = logging.getLogger("redditpilot.drafts")


def body_for_publishing(draft: Draft) -> str:
    """The exact body that would be submitted to Reddit.

    The disclosure field is appended if it is not already present, so the
    disclosure can never be silently dropped at publish time.
    """
    body = draft.body.rstrip()
    disclosure = (draft.disclosure or "").strip()
    if disclosure and disclosure.lower() not in body.lower():
        return f"{body}\n\n{disclosure}"
    return body


def _add_revision(db: Session, draft: Draft, note: str) -> None:
    db.add(
        DraftRevision(
            draft_id=draft.id,
            version=draft.version,
            title=draft.title,
            body=draft.body,
            disclosure=draft.disclosure,
            link_url=draft.link_url,
            change_note=note,
            content_hash=draft.content_hash,
        )
    )


def create_generated_draft(
    db: Session,
    *,
    project: Project,
    subreddit: Subreddit,
    generated: GeneratedPost,
    objective: str,
    topic: str,
    post_type: str,
    model: str,
    source: str = "studio",
    parent_draft_id: int | None = None,
    commit: bool = True,
) -> Draft:
    draft = Draft(
        project_id=project.id,
        subreddit_id=subreddit.id,
        title=generated.title.strip(),
        body=generated.body.strip(),
        disclosure=generated.disclosure.strip(),
        link_url=generated.link_url,
        objective=objective,
        post_type=post_type,
        topic=topic,
        status=DraftStatus.PENDING_REVIEW.value,
        promotional_intensity=generated.promotional_intensity,
        relevance=generated.relevance.strip(),
        rule_violations=generated.potential_rule_violations,
        warnings=generated.warnings,
        model=model,
        source=source,
        parent_draft_id=parent_draft_id,
        version=1,
    )
    draft.content_hash = content_hash(draft.title, draft.body, draft.disclosure, draft.link_url)
    draft.project = project
    draft.subreddit = subreddit
    db.add(draft)
    db.flush()

    # Policy gate: promotional drafts for communities that prohibit promotion
    # are refused before they enter the queue.
    if (
        subreddit.self_promotion_policy == "prohibited"
        and is_promotional(draft)
    ):
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                f"r/{subreddit.name} prohibits promotional content, so this draft was not saved. "
                "Remove the project mention/link, or pick a different community."
            ),
        )

    report = evaluate_draft(db, draft, stage="generation")
    draft.compliance_snapshot = report
    draft.warnings = list(
        dict.fromkeys(
            (generated.warnings or [])
            + [i["message"] for i in report["issues"] if i["severity"] != "blocker"]
        )
    )
    draft.rule_violations = [
        i["message"] for i in report["issues"] if i["severity"] == "blocker"
    ]

    _add_revision(db, draft, "Initial AI generation")
    if commit:
        db.commit()
        db.refresh(draft)
        log_activity(
            db,
            "draft.generated",
            f"Generated draft #{draft.id} for r/{subreddit.name}",
            entity_type="draft",
            entity_id=draft.id,
        )
    else:
        db.flush()
    return draft


def invalidate_approvals(db: Session, draft: Draft, reason: str) -> None:
    now = utcnow()
    changed = False
    for approval in draft.approvals:
        if approval.is_valid and approval.invalidated_at is None:
            approval.is_valid = False
            approval.invalidated_at = now
            approval.invalidation_reason = reason[:300]
            changed = True
    if changed:
        log_activity(
            db,
            "approval.invalidated",
            f"Approval for draft #{draft.id} invalidated: {reason}",
            entity_type="draft",
            entity_id=draft.id,
            level="warning",
            commit=False,
        )


def update_draft(
    db: Session,
    draft: Draft,
    *,
    title: str | None = None,
    body: str | None = None,
    disclosure: str | None = None,
    link_url: str | None = None,
    clear_link: bool = False,
    change_note: str = "",
    regenerate: bool = False,
) -> Draft:
    if draft.status == DraftStatus.PUBLISHED.value:
        raise HTTPException(status_code=409, detail="Published drafts cannot be edited. Duplicate it for a new context.")
    if draft.published_post and draft.published_post.status == "published":
        raise HTTPException(status_code=409, detail="Published drafts cannot be edited.")

    new_title = title if title is not None else draft.title
    new_body = body if body is not None else draft.body
    new_disclosure = disclosure if disclosure is not None else draft.disclosure
    new_link = link_url if link_url is not None else draft.link_url
    if clear_link:
        new_link = None
    new_hash = content_hash(new_title, new_body, new_disclosure, new_link)

    changed = new_hash != draft.content_hash
    if not changed and not regenerate:
        return draft

    if changed:
        # Invalidate first, based on the old approval. A changed approved draft
        # is never allowed to keep its approval.
        invalidate_approvals(db, draft, "Draft content changed after approval")
        if draft.status in (
            DraftStatus.APPROVED.value,
            DraftStatus.SCHEDULED.value,
            DraftStatus.FAILED.value,
        ):
            draft.status = DraftStatus.PENDING_REVIEW.value
            draft.approved_at = None
        if draft.scheduled_slot and draft.scheduled_slot.status in (
            ScheduleStatus.APPROVED.value,
        ):
            draft.scheduled_slot.status = ScheduleStatus.DRAFT_READY.value

        draft.title = new_title.strip()
        draft.body = new_body.strip()
        draft.disclosure = (new_disclosure or "").strip()
        draft.link_url = new_link
        draft.content_hash = new_hash
        draft.version += 1
        draft.last_error = ""
        _add_revision(db, draft, change_note or "Manual edit")

    refresh_compliance(db, draft, stage="review")
    db.commit()
    db.refresh(draft)
    log_activity(
        db,
        "draft.updated",
        f"Updated draft #{draft.id} (v{draft.version})",
        entity_type="draft",
        entity_id=draft.id,
    )
    return draft


def apply_regeneration(
    db: Session,
    draft: Draft,
    generated: GeneratedPost,
    *,
    model: str,
) -> Draft:
    if draft.status == DraftStatus.PUBLISHED.value:
        raise HTTPException(status_code=409, detail="Published drafts cannot be regenerated.")
    invalidate_approvals(db, draft, "Draft regenerated")
    draft.title = generated.title.strip()
    draft.body = generated.body.strip()
    draft.disclosure = generated.disclosure.strip()
    draft.link_url = generated.link_url
    draft.promotional_intensity = generated.promotional_intensity
    draft.relevance = generated.relevance.strip()
    draft.rule_violations = generated.potential_rule_violations
    draft.warnings = generated.warnings
    draft.model = model
    draft.version += 1
    draft.status = DraftStatus.PENDING_REVIEW.value
    draft.approved_at = None
    draft.last_error = ""
    draft.content_hash = content_hash(draft.title, draft.body, draft.disclosure, draft.link_url)

    if draft.scheduled_slot and draft.scheduled_slot.status in (
        ScheduleStatus.APPROVED.value,
        ScheduleStatus.DRAFT_READY.value,
    ):
        draft.scheduled_slot.status = ScheduleStatus.DRAFT_READY.value

    report = evaluate_draft(db, draft, stage="review")
    draft.compliance_snapshot = report
    draft.warnings = list(
        dict.fromkeys(
            (generated.warnings or [])
            + [i["message"] for i in report["issues"] if i["severity"] != "blocker"]
        )
    )
    draft.rule_violations = [
        i["message"] for i in report["issues"] if i["severity"] == "blocker"
    ]
    _add_revision(db, draft, "AI regeneration")
    db.commit()
    db.refresh(draft)
    log_activity(
        db,
        "draft.regenerated",
        f"Regenerated draft #{draft.id} (v{draft.version})",
        entity_type="draft",
        entity_id=draft.id,
    )
    return draft


def approve_draft(db: Session, draft: Draft, note: str = "") -> Draft:
    if draft.status == DraftStatus.PUBLISHED.value:
        raise HTTPException(status_code=409, detail="This draft is already published.")
    if draft.published_post:
        raise HTTPException(status_code=409, detail="A publication record already exists for this draft.")
    if draft.status == DraftStatus.ARCHIVED.value:
        raise HTTPException(status_code=409, detail="Archived drafts cannot be approved.")
    if draft.status not in (DraftStatus.PENDING_REVIEW.value, DraftStatus.REJECTED.value, DraftStatus.FAILED.value):
        if draft.is_approved:
            return draft  # idempotent approval of the exact same content
        raise HTTPException(status_code=409, detail=f"Drafts in '{draft.status}' cannot be approved.")

    report = evaluate_draft(db, draft, stage="review")
    if report["blockers"]:
        messages = [i["message"] for i in report["issues"] if i["severity"] == "blocker"]
        raise HTTPException(
            status_code=409,
            detail="Fix these compliance blockers before approval: " + " ".join(messages[:4]),
        )

    # Invalidate any old approvals so only one can be current.
    invalidate_approvals(db, draft, "Replaced by a new approval")
    approval = Approval(
        draft_id=draft.id,
        content_hash=draft.content_hash,
        note=note.strip(),
        approved_by="local-user",
        approved_at=utcnow(),
        is_valid=True,
    )
    db.add(approval)
    draft.status = DraftStatus.APPROVED.value
    draft.approved_at = utcnow()
    draft.rejected_at = None
    draft.last_error = ""
    draft.compliance_snapshot = report
    if draft.scheduled_slot and draft.scheduled_slot.status != ScheduleStatus.PUBLISHED.value:
        draft.scheduled_slot.status = ScheduleStatus.APPROVED.value
    db.commit()
    db.refresh(draft)
    log_activity(
        db,
        "draft.approved",
        f"Approved draft #{draft.id} for r/{draft.subreddit.name}",
        entity_type="draft",
        entity_id=draft.id,
    )
    return draft


def reject_draft(db: Session, draft: Draft, reason: str) -> Draft:
    if draft.status == DraftStatus.PUBLISHED.value:
        raise HTTPException(status_code=409, detail="Published drafts cannot be rejected.")
    invalidate_approvals(db, draft, f"Draft rejected: {reason}")
    draft.status = DraftStatus.REJECTED.value
    draft.rejected_at = utcnow()
    if draft.scheduled_slot and draft.scheduled_slot.status != ScheduleStatus.PUBLISHED.value:
        draft.scheduled_slot.status = ScheduleStatus.SKIPPED.value
    db.commit()
    db.refresh(draft)
    log_activity(
        db,
        "draft.rejected",
        f"Rejected draft #{draft.id}: {reason}",
        entity_type="draft",
        entity_id=draft.id,
        level="warning",
    )
    return draft


def archive_draft(db: Session, draft: Draft) -> Draft:
    if draft.status == DraftStatus.PUBLISHED.value:
        raise HTTPException(status_code=409, detail="Published drafts cannot be archived.")
    invalidate_approvals(db, draft, "Draft archived")
    draft.status = DraftStatus.ARCHIVED.value
    draft.archived_at = utcnow()
    if draft.scheduled_slot and draft.scheduled_slot.status != ScheduleStatus.PUBLISHED.value:
        draft.scheduled_slot.status = ScheduleStatus.SKIPPED.value
    db.commit()
    db.refresh(draft)
    log_activity(db, "draft.archived", f"Archived draft #{draft.id}", entity_type="draft", entity_id=draft.id)
    return draft


def delete_draft(db: Session, draft: Draft) -> None:
    if draft.published_post:
        raise HTTPException(
            status_code=409,
            detail="This draft has a publication record and cannot be deleted. Archive it instead.",
        )
    slot = draft.scheduled_slot
    draft_id = draft.id
    if slot:
        slot.draft_id = None
        if slot.status != ScheduleStatus.PUBLISHED.value:
            slot.status = ScheduleStatus.PLANNED.value
    db.delete(draft)
    db.commit()
    log_activity(db, "draft.deleted", f"Deleted draft #{draft_id}", entity_type="draft", entity_id=draft_id)
