from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db, utcnow
from app.models import Draft, SchedulePlan, ScheduledPost, Subreddit, SubredditRule
from app.schemas import SubredditCreate, SubredditUpdate
from app.services.activity import log_activity
from app.services.serialize import (
    get_project,
    get_subreddit,
    serialize_subreddit,
)

router = APIRouter(prefix="/api/subreddits", tags=["subreddits"])


def _sync_rules(subreddit: Subreddit, rules) -> None:
    subreddit.rules.clear()
    for index, rule in enumerate(rules):
        if isinstance(rule, dict):
            title, detail = rule.get("title", ""), rule.get("detail", "")
        else:
            title, detail = rule.title, rule.detail
        subreddit.rules.append(
            SubredditRule(title=str(title).strip(), detail=str(detail).strip(), position=index)
        )


@router.get("")
def list_subreddits(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(Subreddit).order_by(Subreddit.name.asc())
    if project_id:
        query = query.filter(Subreddit.project_id == project_id)
    return {"items": [serialize_subreddit(row) for row in query.all()]}


@router.post("", status_code=201)
def create_subreddit(payload: SubredditCreate, db: Session = Depends(get_db)):
    project = get_project(db, payload.project_id)
    data = payload.model_dump()
    rules = data.pop("rules", [])
    data.pop("project_id", None)
    data["name"] = data["name"].strip()
    subreddit = Subreddit(project_id=project.id, **data)
    db.add(subreddit)
    try:
        db.flush()
        _sync_rules(subreddit, rules)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"r/{payload.name} already exists for this project.",
        ) from exc
    db.refresh(subreddit)
    log_activity(
        db,
        "subreddit.created",
        f"Added r/{subreddit.name} for project '{project.name}'",
        entity_type="subreddit",
        entity_id=subreddit.id,
    )
    return serialize_subreddit(subreddit, project.name)


@router.get("/{subreddit_id}")
def get_subreddit_detail(subreddit_id: int, db: Session = Depends(get_db)):
    return serialize_subreddit(get_subreddit(db, subreddit_id))


@router.patch("/{subreddit_id}")
def update_subreddit(subreddit_id: int, payload: SubredditUpdate, db: Session = Depends(get_db)):
    subreddit = get_subreddit(db, subreddit_id)
    data = payload.model_dump(exclude_unset=True)
    rules = data.pop("rules", None)
    for key, value in data.items():
        setattr(subreddit, key, value)
    if rules is not None:
        _sync_rules(
            subreddit,
            [
                {
                    "title": rule["title"] if isinstance(rule, dict) else rule.title,
                    "detail": rule["detail"] if isinstance(rule, dict) else rule.detail,
                }
                for rule in rules
            ],
        )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"r/{payload.name or subreddit.name} already exists for this project.",
        ) from exc
    db.refresh(subreddit)
    log_activity(
        db,
        "subreddit.updated",
        f"Updated r/{subreddit.name}",
        entity_type="subreddit",
        entity_id=subreddit.id,
    )
    return serialize_subreddit(subreddit)


@router.post("/{subreddit_id}/verify")
def verify_subreddit_rules(subreddit_id: int, db: Session = Depends(get_db)):
    subreddit = get_subreddit(db, subreddit_id)
    subreddit.last_rules_verified_at = utcnow()
    db.commit()
    db.refresh(subreddit)
    log_activity(
        db,
        "subreddit.rules_verified",
        f"Marked rules for r/{subreddit.name} as verified today",
        entity_type="subreddit",
        entity_id=subreddit.id,
    )
    return serialize_subreddit(subreddit)


@router.delete("/{subreddit_id}")
def delete_subreddit(subreddit_id: int, db: Session = Depends(get_db)):
    subreddit = get_subreddit(db, subreddit_id)
    draft_count = db.query(Draft).filter(Draft.subreddit_id == subreddit_id).count()
    schedule_count = (
        db.query(ScheduledPost).filter(ScheduledPost.subreddit_id == subreddit_id).count()
    )
    if draft_count or schedule_count:
        raise HTTPException(
            status_code=409,
            detail=(
                "This community has drafts or scheduled posts and cannot be deleted. "
                "Mark it 'Not recommended' instead to keep the history."
            ),
        )
    plan = db.query(SchedulePlan).filter(SchedulePlan.subreddit_id == subreddit_id).first()
    if plan:
        raise HTTPException(
            status_code=409,
            detail="This community is used by the weekly schedule. Update or disable the schedule plan first.",
        )
    db.delete(subreddit)
    db.commit()
    log_activity(db, "subreddit.deleted", f"Deleted r/{subreddit.name}")
    return {"ok": True, "message": "Subreddit removed."}
