"""Manual and authorized-API publishing.

Both paths require a current human approval for the exact content hash. There
are no automatic retries after a submission attempt, and a draft can have at
most one publication record (enforced by a unique constraint).
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.db import utcnow
from app.enums import DraftStatus, PublishedStatus, ScheduleStatus
from app.models import Draft, PublishedPost
from app.services.activity import log_activity
from app.services.compliance import api_publish_blockers, evaluate_draft
from app.services.draft_service import body_for_publishing
from app.services.settings_service import get_reddit_credentials, get_settings_row

logger = logging.getLogger("redditpilot.publishing")
_publish_lock = threading.Lock()


def reddit_submit_url(subreddit: str, title: str, body: str) -> str:
    return (
        f"https://www.reddit.com/r/{quote(subreddit)}/submit?"
        f"title={quote(title)}&text={quote(body)}&type=self"
    )


def _ensure_publishable(db: Session, draft: Draft) -> dict:
    if draft.published_post:
        raise HTTPException(
            status_code=409,
            detail="A publication record already exists for this draft. A draft can only be published once.",
        )
    if draft.status == DraftStatus.PUBLISHED.value:
        raise HTTPException(status_code=409, detail="This draft is already published.")
    if not draft.is_approved:
        raise HTTPException(
            status_code=409,
            detail="This exact version is not approved. Review it and approve it before publishing.",
        )
    settings_row = get_settings_row(db)
    if draft.scheduled_slot and settings_row.scheduling_paused:
        raise HTTPException(
            status_code=409,
            detail="Scheduling is paused. Resume scheduling in Settings before publishing a scheduled draft.",
        )
    report = evaluate_draft(db, draft, stage="publish")
    blockers = [i["message"] for i in report["issues"] if i["severity"] == "blocker"]
    if blockers:
        raise HTTPException(
            status_code=409,
            detail="Publishing blocked by compliance checks: " + " ".join(blockers[:4]),
        )
    return report


def manual_prepare(db: Session, draft: Draft) -> dict:
    report = _ensure_publishable(db, draft)
    body = body_for_publishing(draft)
    return {
        "draft_id": draft.id,
        "subreddit": draft.subreddit.name,
        "title": draft.title,
        "body": body,
        "submit_url": reddit_submit_url(draft.subreddit.name, draft.title, body),
        "compliance": report,
        "instructions": [
            "Open the Reddit submission page and review every field.",
            "Confirm the community rules and flair yourself; RedditPilot does not submit anything.",
            "After you publish on Reddit, paste the post URL below to record it.",
        ],
        "disclosure_included": draft.disclosure.strip().lower() in body.lower()
        if draft.disclosure.strip()
        else True,
    }


def _validate_reddit_url(url: str, subreddit_name: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.netloc.lower() not in {"www.reddit.com", "reddit.com", "old.reddit.com"}:
        raise HTTPException(status_code=422, detail="The URL must be a reddit.com post URL.")
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 2 or path_parts[0].lower() != "r":
        raise HTTPException(status_code=422, detail="The URL must look like https://www.reddit.com/r/<subreddit>/comments/...")
    if path_parts[1].lower() != subreddit_name.lower():
        raise HTTPException(
            status_code=422,
            detail=f"The URL is for r/{path_parts[1]}, but this draft targets r/{subreddit_name}.",
        )
    if "comments" not in [p.lower() for p in path_parts]:
        raise HTTPException(status_code=422, detail="That does not look like a published Reddit post URL.")
    return url.strip()


def _record_publication(
    db: Session,
    *,
    draft: Draft,
    url: str | None,
    reddit_post_id: str | None,
    mode: str,
    status: str = PublishedStatus.PUBLISHED.value,
    published_at: datetime | None = None,
    note: str = "",
) -> PublishedPost:
    post = PublishedPost(
        draft_id=draft.id,
        project_id=draft.project_id,
        subreddit_id=draft.subreddit_id,
        reddit_post_id=reddit_post_id,
        url=url,
        title=draft.title,
        subreddit_name=draft.subreddit.name,
        published_at=published_at or utcnow(),
        mode=mode,
        status=status,
        notes=note,
    )
    db.add(post)
    if status == PublishedStatus.PUBLISHED.value:
        draft.status = DraftStatus.PUBLISHED.value
        if draft.scheduled_slot:
            draft.scheduled_slot.status = ScheduleStatus.PUBLISHED.value
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A publication record for this draft already exists. It was not published twice.",
        )
    db.refresh(post)
    return post


def confirm_manual_publication(
    db: Session,
    draft: Draft,
    *,
    url: str,
    note: str = "",
    published_at: datetime | None = None,
) -> PublishedPost:
    with _publish_lock:
        # Re-read after acquiring the lock to close a double-click race.
        db.refresh(draft)
        _ensure_publishable(db, draft)
        clean_url = _validate_reddit_url(url, draft.subreddit.name)
        existing_url = db.query(PublishedPost).filter(PublishedPost.url == clean_url).first()
        if existing_url:
            raise HTTPException(
                status_code=409,
                detail="That Reddit URL is already recorded for another publication.",
            )
        if published_at:
            if published_at.tzinfo:
                published_at = published_at.astimezone(timezone.utc).replace(tzinfo=None)
        post = _record_publication(
            db,
            draft=draft,
            url=clean_url,
            reddit_post_id=None,
            mode="manual",
            published_at=published_at,
            note=note,
        )
        log_activity(
            db,
            "draft.published_manual",
            f"Recorded manual publication of draft #{draft.id} at {clean_url}",
            entity_type="draft",
            entity_id=draft.id,
        )
        return post


def build_reddit(credentials: dict[str, str | None]):
    """Create an authorized PRAW client. Imported lazily to keep startup fast."""
    try:
        import praw
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PRAW is not installed. Run pip install -r requirements.txt.") from exc

    if not credentials.get("client_id") or not credentials.get("client_secret"):
        raise RuntimeError("Reddit client ID/secret are missing.")
    if not credentials.get("user_agent"):
        raise RuntimeError("A descriptive Reddit user_agent is required (for example redditpilot/1.0 by u/yourname).")

    kwargs = {
        "client_id": credentials["client_id"],
        "client_secret": credentials["client_secret"],
        "user_agent": credentials["user_agent"],
        "validate_on_submit": True,
        "timeout": app_settings.reddit_timeout_seconds,
    }
    if credentials.get("refresh_token"):
        kwargs["refresh_token"] = credentials["refresh_token"]
    else:
        if not credentials.get("username") or not credentials.get("password"):
            raise RuntimeError("Provide a refresh token, or a Reddit username and password.")
        kwargs["username"] = credentials["username"]
        kwargs["password"] = credentials["password"]
    return praw.Reddit(**kwargs)


def verify_reddit_connection(db: Session, reddit=None) -> dict:
    settings_row = get_settings_row(db)
    credentials = get_reddit_credentials(db)
    if not credentials:
        raise HTTPException(
            status_code=400,
            detail="No Reddit API credentials are configured. Add them in Settings first.",
        )
    if not settings_row.api_publishing_enabled:
        raise HTTPException(
            status_code=403,
            detail="API publishing is disabled. Enable it explicitly in Settings after reviewing Reddit's API terms.",
        )
    try:
        client = reddit or build_reddit(credentials)
        me = client.user.me()
        username = getattr(me, "name", None) or str(me)
    except Exception as exc:  # noqa: BLE001
        from app.models import APIConnection

        connection = db.query(APIConnection).filter(APIConnection.provider == "reddit").first()
        if connection:
            connection.status = "error"
            connection.last_error = str(exc)[:500]
            db.commit()
        raise HTTPException(
            status_code=400,
            detail="Reddit authentication failed. Check the credentials, app type and scopes. No post was submitted.",
        ) from exc

    from app.models import APIConnection

    connection = db.query(APIConnection).filter(APIConnection.provider == "reddit").first()
    if connection:
        connection.status = "connected"
        connection.username = username
        connection.last_verified_at = utcnow()
        connection.last_error = ""
        db.commit()
    log_activity(db, "reddit.verified", f"Verified Reddit account u/{username}")
    return {"username": username, "status": "connected"}


def api_publish(db: Session, draft: Draft, *, note: str = "") -> dict:
    settings_row = get_settings_row(db)
    if settings_row.publishing_mode != "api":
        raise HTTPException(status_code=403, detail="Publishing mode is Manual. Switch to API mode in Settings.")
    if not settings_row.api_publishing_enabled:
        raise HTTPException(status_code=403, detail="API publishing is disabled. It is off by default.")
    credentials = get_reddit_credentials(db)
    if not credentials:
        raise HTTPException(status_code=400, detail="Reddit API credentials are not configured.")

    with _publish_lock:
        db.refresh(draft)
        blockers = api_publish_blockers(db, draft)
        if blockers:
            raise HTTPException(
                status_code=409,
                detail="API publishing blocked: " + " ".join(dict.fromkeys(blockers))[:1500],
            )
        report = _ensure_publishable(db, draft)
        if not draft.is_approved:
            raise HTTPException(status_code=409, detail="Draft approval is missing or stale.")

        try:
            reddit = build_reddit(credentials)
            me = reddit.user.me()
            account = getattr(me, "name", None)
            if credentials.get("username") and account and account.lower() != credentials["username"].lower():
                raise HTTPException(
                    status_code=403,
                    detail=f"Connected account u/{account} does not match the configured username. Nothing was submitted.",
                )
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Reddit authentication failed before submission")
            log_activity(
                db,
                "reddit.auth_failed",
                f"Reddit authentication failed before submission: {str(exc)[:300]}",
                level="error",
            )
            raise HTTPException(
                status_code=400,
                detail="Reddit authentication failed before submission. No post was submitted.",
            ) from exc

        body = body_for_publishing(draft)
        log_activity(
            db,
            "reddit.submission_started",
            f"Submitting draft #{draft.id} to r/{draft.subreddit.name} via API",
            entity_type="draft",
            entity_id=draft.id,
        )

        submission = None
        try:
            submission = reddit.subreddit(draft.subreddit.name).submit(
                title=draft.title, selftext=body
            )
            post_id = getattr(submission, "id", None)
            url = getattr(submission, "url", None)
            if not url and post_id:
                url = f"https://www.reddit.com/r/{draft.subreddit.name}/comments/{post_id}/"
            if not url:
                raise RuntimeError("Reddit returned no permalink for the submission.")
            post = _record_publication(
                db,
                draft=draft,
                url=url,
                reddit_post_id=post_id,
                mode="api",
                note=note,
            )
            log_activity(
                db,
                "draft.published_api",
                f"Published draft #{draft.id} via Reddit API: {url}",
                entity_type="draft",
                entity_id=draft.id,
            )
            return {
                "published_post": post,
                "compliance": report,
                "warning": "",
                "message": "Published through the authorized Reddit API.",
            }
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            # The submission may have reached Reddit before the connection
            # failed. Do not retry. Record an uncertain result for manual review.
            logger.exception("Uncertain Reddit submission result for draft %s", draft.id)
            draft.status = DraftStatus.FAILED.value
            draft.last_error = (
                "Reddit submission result was uncertain. Check your Reddit profile and enter "
                "the post URL under Published Posts. Do not retry blindly."
            )
            if draft.scheduled_slot:
                draft.scheduled_slot.status = ScheduleStatus.FAILED.value
                draft.scheduled_slot.error = draft.last_error
            post = _record_publication(
                db,
                draft=draft,
                url=None,
                reddit_post_id=None,
                mode="api",
                status=PublishedStatus.UNCERTAIN.value,
                note=f"Submission error: {str(exc)[:500]}",
            )
            log_activity(
                db,
                "reddit.submission_uncertain",
                f"Draft #{draft.id}: submission result uncertain. Verify on Reddit before retrying.",
                entity_type="draft",
                entity_id=draft.id,
                level="error",
            )
            return {
                "published_post": post,
                "compliance": report,
                "warning": (
                    "The submission result is uncertain. RedditPilot will not retry automatically. "
                    "Check Reddit, then confirm the URL from Published Posts."
                ),
                "message": "Submission result uncertain.",
            }
