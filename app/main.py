"""RedditPilot FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import BASE_DIR, settings
from app.db import Base, SessionLocal, engine, utcnow
from app.routers import (
    analytics,
    drafts,
    overview,
    projects,
    published,
    publishing,
    schedule,
    settings as settings_router,
    subreddits,
)
from app.services.scheduler import run_tick

logger = logging.getLogger("redditpilot")
scheduler: BackgroundScheduler | None = None


def configure_logging() -> None:
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )
    root = logging.getLogger()
    if not root.handlers:
        root.setLevel(logging.INFO)
        file_handler = RotatingFileHandler(
            log_dir / "redditpilot.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root.addHandler(file_handler)
        root.addHandler(stream_handler)
    # PRAW is chatty at DEBUG and could include request details.
    logging.getLogger("praw").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def scheduler_job() -> None:
    db = SessionLocal()
    try:
        result = run_tick(db)
        if result.get("generated") or result.get("failed"):
            logger.info("Scheduler tick: %s", result)
    except Exception:  # noqa: BLE001
        logger.exception("Scheduler tick failed")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    Base.metadata.create_all(bind=engine)
    logger.info("RedditPilot starting (database=%s)", settings.database_url)
    global scheduler
    if not settings.disable_scheduler:
        scheduler = BackgroundScheduler(timezone="UTC", daemon=True)
        scheduler.add_job(
            scheduler_job,
            "interval",
            minutes=max(1, settings.scheduler_interval_minutes),
            id="weekly-slot-tick",
            max_instances=1,
            coalesce=True,
            next_run_time=utcnow() + timedelta(seconds=15),
        )
        scheduler.start()
        logger.info("Scheduler started (every %s minutes)", settings.scheduler_interval_minutes)
    yield
    if scheduler:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


app = FastAPI(
    title="RedditPilot",
    description=(
        "A human-in-the-loop Reddit content workspace. Generates with Gemini, "
        "requires approval, and never publishes automatically."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


for router in (
    projects.router,
    subreddits.router,
    drafts.router,
    publishing.router,
    published.router,
    schedule.router,
    analytics.router,
    overview.router,
    settings_router.router,
):
    app.include_router(router)


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "app": "RedditPilot",
        "time_utc": utcnow().isoformat() + "Z",
        "scheduler_enabled": not settings.disable_scheduler,
        "scheduler_note": "Scheduling only creates drafts for human review.",
    }


@app.get("/api/meta")
def meta():
    from app.enums import OBJECTIVES, POST_TYPES, WEEKDAYS

    return {
        "objectives": OBJECTIVES,
        "post_types": POST_TYPES,
        "weekdays": WEEKDAYS,
        "draft_statuses": [
            "Pending Review",
            "Approved",
            "Rejected",
            "Scheduled",
            "Published",
            "Failed",
            "Archived",
        ],
        "publishing_nevers": [
            "No automatic publishing",
            "No multiple-account manipulation",
            "No scraping or mass-posting",
        ],
    }


@app.exception_handler(Exception)
async def unhandled_exception(request, exc):  # pragma: no cover - safety net
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected server error occurred. Check logs/redditpilot.log for details."},
    )


dist = settings.frontend_dist
assets = dist / "assets"
if assets.exists():
    app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

index_file = dist / "index.html"
if index_file.exists():
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found.")
        return HTMLResponse(index_file.read_text(encoding="utf-8"))
else:
    @app.get("/", include_in_schema=False)
    async def frontend_missing():
        return HTMLResponse(
            """
            <html><body style="background:#0d0e10;color:#e8e4da;font-family:Georgia,serif;padding:48px;line-height:1.6">
            <h1>RedditPilot API is running</h1>
            <p>The dashboard has not been built yet. From the project directory run:</p>
            <pre style="background:#181a1e;padding:16px;border-radius:8px">cd frontend
npm install
npm run build</pre>
            <p>Then restart the server and open <a style="color:#e07a4f" href="http://127.0.0.1:8000">http://127.0.0.1:8000</a>.</p>
            <p>API docs: <a style="color:#e07a4f" href="/docs">/docs</a></p>
            </body></html>
            """
        )
