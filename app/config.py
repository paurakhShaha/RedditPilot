"""Application configuration.

Secrets are read from the environment / .env. The Gemini key and Reddit
credentials entered in the dashboard are stored encrypted in the database and
are never returned by the API.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(BASE_DIR / ".env")


class Settings:
    app_name: str = "RedditPilot"
    environment: str = os.getenv("APP_ENV", "development")
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "8000"))

    database_url: str = os.getenv(
        "DATABASE_URL", f"sqlite:///{(DATA_DIR / 'redditpilot.db').as_posix()}"
    )

    # Fernet key used to encrypt credentials at rest. If omitted, a key is
    # generated once in data/.secret_key. Losing it makes stored credentials
    # unreadable; the README explains how to reset them.
    secret_key: str | None = os.getenv("APP_SECRET_KEY")
    secret_key_file: Path = DATA_DIR / ".secret_key"

    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
    default_gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # Scheduler runs in a background thread. Tests disable it.
    disable_scheduler: bool = os.getenv("DISABLE_SCHEDULER", "0") == "1"
    scheduler_interval_minutes: int = int(os.getenv("SCHEDULER_INTERVAL_MINUTES", "15"))

    # Networks may be blocked in some environments; requests time out.
    gemini_timeout_seconds: int = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "90"))
    reddit_timeout_seconds: int = int(os.getenv("REDDIT_TIMEOUT_SECONDS", "30"))

    frontend_dist: Path = BASE_DIR / "frontend" / "dist"

    def requires_secret_key(self) -> bool:
        return bool(self.secret_key)


settings = Settings()


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return settings
