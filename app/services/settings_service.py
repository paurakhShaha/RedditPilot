"""Settings access and credential resolution (never exposes secrets)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.db import utcnow
from app.models import APIConnection, UserSettings
from app.security import decrypt_secret, encrypt_secret
from app.services.serialize import get_settings_row, iso


def get_gemini_key(db: Session) -> str | None:
    row = get_settings_row(db)
    try:
        stored = decrypt_secret(row.gemini_api_key_enc)
    except ValueError:
        stored = None
    return stored or app_settings.gemini_api_key


def get_reddit_credentials(db: Session) -> dict[str, str | None] | None:
    connection = db.query(APIConnection).filter(APIConnection.provider == "reddit").first()
    if not connection:
        return None
    try:
        creds = {
            "client_id": decrypt_secret(connection.client_id_enc),
            "client_secret": decrypt_secret(connection.client_secret_enc),
            "username": decrypt_secret(connection.username_enc),
            "password": decrypt_secret(connection.password_enc),
            "refresh_token": decrypt_secret(connection.refresh_token_enc),
            "user_agent": connection.user_agent,
        }
    except ValueError:
        return None
    if not creds["client_id"] or not creds["client_secret"]:
        return None
    return creds


def get_or_create_connection(db: Session) -> APIConnection:
    connection = db.query(APIConnection).filter(APIConnection.provider == "reddit").first()
    if connection is None:
        connection = APIConnection(provider="reddit", status="disconnected")
        db.add(connection)
        db.commit()
        db.refresh(connection)
    return connection


def save_reddit_credentials(db: Session, values: dict[str, str]) -> APIConnection:
    connection = get_or_create_connection(db)
    if values.get("client_id"):
        connection.client_id_enc = encrypt_secret(values["client_id"])
    if values.get("client_secret"):
        connection.client_secret_enc = encrypt_secret(values["client_secret"])
    if values.get("username"):
        connection.username_enc = encrypt_secret(values["username"])
        connection.username = values["username"]
    if values.get("password"):
        connection.password_enc = encrypt_secret(values["password"])
    if values.get("refresh_token"):
        connection.refresh_token_enc = encrypt_secret(values["refresh_token"])
    if values.get("user_agent"):
        connection.user_agent = values["user_agent"]
    connection.status = "unverified"
    connection.last_error = ""
    db.commit()
    db.refresh(connection)
    return connection


def clear_reddit_credentials(db: Session) -> None:
    connection = get_or_create_connection(db)
    connection.client_id_enc = None
    connection.client_secret_enc = None
    connection.password_enc = None
    connection.refresh_token_enc = None
    connection.username_enc = None
    connection.user_agent = None
    connection.username = None
    connection.status = "disconnected"
    connection.last_verified_at = None
    connection.last_error = ""
    db.commit()


def serialize_settings(db: Session) -> dict[str, Any]:
    row = get_settings_row(db)
    connection = (
        db.query(APIConnection).filter(APIConnection.provider == "reddit").first()
    )
    key_from_env = bool(app_settings.gemini_api_key)
    return {
        "default_project_id": row.default_project_id,
        "gemini_model": row.gemini_model,
        "gemini_key_configured": bool(row.gemini_api_key_enc) or key_from_env,
        "gemini_key_source": "database" if row.gemini_api_key_enc else ("environment" if key_from_env else None),
        "weekly_frequency": row.weekly_frequency,
        "publishing_day": row.publishing_day,
        "publishing_time": row.publishing_time,
        "timezone": row.timezone,
        "scheduling_paused": row.scheduling_paused,
        "publishing_mode": row.publishing_mode,
        "api_publishing_enabled": row.api_publishing_enabled,
        "generation_temperature": row.generation_temperature,
        "max_promo_score": row.max_promo_score,
        "avoid_emojis": row.avoid_emojis,
        "default_include_link": row.default_include_link,
        "extra_generation_notes": row.extra_generation_notes,
        "reddit_connected": bool(connection and connection.status == "connected"),
        "reddit_username": connection.username if connection else None,
        "reddit_status": connection.status if connection else "disconnected",
        "reddit_last_verified_at": iso(connection.last_verified_at) if connection else None,
        "reddit_last_error": connection.last_error if connection else "",
        "reddit_credentials_configured": bool(
            connection
            and (connection.client_id_enc or connection.client_secret_enc)
        ),
        "scheduler_note": "The scheduler only generates drafts for review. It never publishes.",
        "server_time_utc": iso(utcnow()),
    }


def local_now(db: Session) -> datetime:
    """Current time in the configured project timezone (timezone-aware)."""
    from zoneinfo import ZoneInfo

    row = get_settings_row(db)
    return datetime.now(ZoneInfo(row.timezone))
