from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Project
from app.schemas import ProjectCreate, ProjectUpdate
from app.services.activity import log_activity
from app.services.serialize import get_project, get_settings_row, serialize_project

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
def list_projects(
    include_archived: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    query = db.query(Project).order_by(Project.created_at.asc())
    if not include_archived:
        query = query.filter(Project.is_archived.is_(False))
    return {"items": [serialize_project(db, project) for project in query.all()]}


@router.post("", status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(**payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    settings_row = get_settings_row(db)
    if settings_row.default_project_id is None:
        settings_row.default_project_id = project.id
        db.commit()
    log_activity(
        db,
        "project.created",
        f"Created project '{project.name}'",
        entity_type="project",
        entity_id=project.id,
    )
    return serialize_project(db, project)


@router.get("/{project_id}")
def get_project_detail(project_id: int, db: Session = Depends(get_db)):
    return serialize_project(db, get_project(db, project_id))


@router.patch("/{project_id}")
def update_project(project_id: int, payload: ProjectUpdate, db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if key in {"name", "website_url"} and value is None:
            continue
        setattr(project, key, value)
    db.commit()
    db.refresh(project)
    log_activity(
        db,
        "project.updated",
        f"Updated project '{project.name}'",
        entity_type="project",
        entity_id=project.id,
    )
    return serialize_project(db, project)


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    from app.models import Draft, PublishedPost, SchedulePlan, Subreddit

    project = get_project(db, project_id)
    draft_count = db.query(Draft).filter(Draft.project_id == project_id).count()
    published_count = db.query(PublishedPost).filter(PublishedPost.project_id == project_id).count()
    if draft_count or published_count:
        raise HTTPException(
            status_code=409,
            detail=(
                "This project has drafts or publishing history and cannot be deleted. "
                "Archive it instead to preserve the audit trail."
            ),
        )
    subreddit_count = db.query(Subreddit).filter(Subreddit.project_id == project_id).count()
    if subreddit_count:
        raise HTTPException(
            status_code=409,
            detail="Remove the project's subreddits first, or archive the project instead.",
        )
    settings_row = get_settings_row(db)
    if settings_row.default_project_id == project_id:
        settings_row.default_project_id = None
    db.query(SchedulePlan).filter(SchedulePlan.project_id == project_id).delete()
    db.delete(project)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="The project is still referenced and cannot be deleted.") from exc
    log_activity(db, "project.deleted", f"Deleted project #{project_id}")
    return {"ok": True, "message": "Project deleted."}
