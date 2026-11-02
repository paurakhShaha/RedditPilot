"""Persistent activity log."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import ActivityLog


def log_activity(
    db: Session,
    action: str,
    message: str = "",
    *,
    entity_type: str = "",
    entity_id: int | None = None,
    level: str = "info",
    actor: str = "local-user",
    commit: bool = True,
) -> ActivityLog:
    entry = ActivityLog(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        message=message,
        level=level,
    )
    db.add(entry)
    if commit:
        db.commit()
    return entry
