"""Shared helpers for content hashing, serialization and lookups."""

from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import Draft, Project, Subreddit, UserSettings
from app.services.activity import log_activity


def content_hash(title: str, body: str, disclosure: str = "", link_url: str | None = None) -> str:
    normalized = "\n".join(
        [
            re.sub(r"\s+", " ", (title or "").strip().lower()),
            re.sub(r"\s+", " ", (body or "").strip().lower()),
            re.sub(r"\s+", " ", (disclosure or "").strip().lower()),
            (link_url or "").strip().lower(),
        ]
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    # Stored timestamps are naive UTC. Mark them explicitly for the browser.
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def get_project(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def get_subreddit(db: Session, subreddit_id: int) -> Subreddit:
    subreddit = db.get(Subreddit, subreddit_id)
    if not subreddit:
        raise HTTPException(status_code=404, detail="Subreddit not found")
    return subreddit


def get_draft(db: Session, draft_id: int) -> Draft:
    draft = db.get(Draft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft


def get_settings_row(db: Session) -> UserSettings:
    row = db.get(UserSettings, 1)
    if row is None:
        row = UserSettings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def project_counts(db: Session, project_id: int) -> dict[str, int]:
    from app.models import Draft, PublishedPost, Subreddit

    return {
        "draft_count": db.scalar(select(func.count(Draft.id)).where(Draft.project_id == project_id)) or 0,
        "published_count": db.scalar(
            select(func.count(PublishedPost.id)).where(
                PublishedPost.project_id == project_id,
                PublishedPost.status == "published",
            )
        )
        or 0,
        "subreddit_count": db.scalar(
            select(func.count(Subreddit.id)).where(Subreddit.project_id == project_id)
        )
        or 0,
    }


def serialize_project(db: Session, project: Project) -> dict[str, Any]:
    return {
        "id": project.id,
        "name": project.name,
        "website_url": project.website_url,
        "description": project.description,
        "target_audience": project.target_audience,
        "product_category": project.product_category,
        "unique_selling_proposition": project.unique_selling_proposition,
        "features": project.features,
        "pricing_info": project.pricing_info,
        "brand_voice": project.brand_voice,
        "marketing_objectives": project.marketing_objectives,
        "disclosure_statement": project.disclosure_statement,
        "restricted_claims": project.restricted_claims,
        "is_archived": project.is_archived,
        "created_at": iso(project.created_at),
        "updated_at": iso(project.updated_at),
        **project_counts(db, project.id),
    }


def serialize_subreddit(subreddit: Subreddit, project_name: str | None = None) -> dict[str, Any]:
    rules = [
        {"id": rule.id, "title": rule.title, "detail": rule.detail, "position": rule.position}
        for rule in subreddit.rules
    ]
    rules_text = "\n".join(
        f"{r['title']}: {r['detail']}".strip() for r in rules if r["title"]
    )
    verified_age = None
    if subreddit.last_rules_verified_at:
        verified_age = max(0, (utcnow() - subreddit.last_rules_verified_at).days)
    return {
        "id": subreddit.id,
        "project_id": subreddit.project_id,
        "project_name": project_name or (subreddit.project.name if subreddit.project else ""),
        "name": subreddit.name,
        "description": subreddit.description,
        "self_promotion_policy": subreddit.self_promotion_policy,
        "links_policy": subreddit.links_policy,
        "allowed_post_types": subreddit.allowed_post_types or [],
        "min_account_age_days": subreddit.min_account_age_days,
        "min_karma": subreddit.min_karma,
        "last_rules_verified_at": iso(subreddit.last_rules_verified_at),
        "rules_verified_age_days": verified_age,
        "notes": subreddit.notes,
        "approval_status": subreddit.approval_status,
        "rules": rules,
        "rules_text": rules_text,
        "created_at": iso(subreddit.created_at),
        "updated_at": iso(subreddit.updated_at),
    }


def serialize_approval(approval) -> dict[str, Any] | None:
    if approval is None:
        return None
    return {
        "id": approval.id,
        "content_hash": approval.content_hash,
        "approved_by": approval.approved_by,
        "approved_at": iso(approval.approved_at),
        "note": approval.note,
        "is_valid": approval.is_valid,
        "invalidated_at": iso(approval.invalidated_at),
        "invalidation_reason": approval.invalidation_reason,
    }


def serialize_published(post) -> dict[str, Any]:
    ctr = None
    if post.views and post.website_visits:
        ctr = round(post.website_visits / post.views * 100, 2)
    return {
        "id": post.id,
        "draft_id": post.draft_id,
        "project_id": post.project_id,
        "subreddit_id": post.subreddit_id,
        "subreddit_name": post.subreddit_name,
        "reddit_post_id": post.reddit_post_id,
        "url": post.url,
        "title": post.title,
        "published_at": iso(post.published_at),
        "mode": post.mode,
        "status": post.status,
        "upvotes": post.upvotes,
        "comments": post.comments,
        "views": post.views,
        "website_visits": post.website_visits,
        "referral_visits": post.referral_visits,
        "ctr": ctr,
        "notes": post.notes,
        "metrics_updated_at": iso(post.metrics_updated_at),
        "created_at": iso(post.created_at),
    }


def serialize_draft(draft: Draft, include_body: bool = True) -> dict[str, Any]:
    approval = draft.current_approval
    slot = draft.scheduled_slot
    payload: dict[str, Any] = {
        "id": draft.id,
        "project_id": draft.project_id,
        "project_name": draft.project.name if draft.project else "",
        "subreddit_id": draft.subreddit_id,
        "subreddit_name": draft.subreddit.name if draft.subreddit else "",
        "title": draft.title,
        "disclosure": draft.disclosure,
        "link_url": draft.link_url,
        "objective": draft.objective,
        "post_type": draft.post_type,
        "topic": draft.topic,
        "status": draft.status,
        "promotional_intensity": draft.promotional_intensity,
        "relevance": draft.relevance,
        "rule_violations": draft.rule_violations or [],
        "warnings": draft.warnings or [],
        "compliance": draft.compliance_snapshot or {},
        "model": draft.model,
        "source": draft.source,
        "parent_draft_id": draft.parent_draft_id,
        "content_hash": draft.content_hash,
        "version": draft.version,
        "approved_at": iso(draft.approved_at),
        "rejected_at": iso(draft.rejected_at),
        "archived_at": iso(draft.archived_at),
        "last_error": draft.last_error,
        "created_at": iso(draft.created_at),
        "updated_at": iso(draft.updated_at),
        "approval": serialize_approval(approval),
        "is_approved": draft.is_approved,
        "revision_count": len(draft.revisions),
        "published_post": serialize_published(draft.published_post)
        if draft.published_post
        else None,
        "scheduled_slot": {
            "id": slot.id,
            "slot_start": iso(slot.slot_start),
            "status": slot.status,
        }
        if slot
        else None,
    }
    if include_body:
        payload["body"] = draft.body
    else:
        payload["body_excerpt"] = html.unescape(draft.body[:280].replace("\n", " "))
    return payload


def log_and_raise(db: Session, status_code: int, message: str, action: str = "error") -> None:
    log_activity(db, action=action, message=message, level="warning")
    raise HTTPException(status_code=status_code, detail=message)
