"""Create or upgrade the RedditPilot database.

Usage:
    python scripts/init_db.py
    python scripts/init_db.py --reset

The script uses Alembic as the source of truth. If the database was created by
the application's ``create_all`` startup path and has no ``alembic_version``
table yet, the existing schema is stamped at the current head before upgrading.
``--reset`` moves the current SQLite database into ``data/backups`` first.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, inspect  # noqa: E402

from app.config import DATA_DIR, settings  # noqa: E402


def sqlite_database_path() -> Path | None:
    if not settings.database_url.startswith("sqlite"):
        return None
    raw = settings.database_url.replace("sqlite:///", "", 1)
    path = Path(raw)
    return path if path.is_absolute() else (ROOT / path)


def move_existing_database(path: Path) -> None:
    if not path.exists():
        return
    backups = DATA_DIR / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backups / f"pre-reset-{path.stem}-{stamp}{path.suffix}"
    shutil.move(str(path), str(target))
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(path) + suffix)
        if sidecar.exists():
            sidecar.unlink()
    print(f"Moved the existing database to {target}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialise the RedditPilot database.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Move the existing SQLite database to data/backups, then create a fresh one.",
    )
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sqlite_path = sqlite_database_path()
    if sqlite_path is not None:
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        if args.reset:
            move_existing_database(sqlite_path)
    elif args.reset:
        print("--reset only applies to SQLite databases. Refusing to drop a server database.")
        return 2

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

    engine = create_engine(settings.database_url, future=True)
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        if tables and "alembic_version" not in tables:
            print("Existing tables found without an Alembic version; stamping the current head.")
            command.stamp(config, "head")
    finally:
        engine.dispose()

    command.upgrade(config, "head")
    print(f"Database ready: {settings.database_url}")
    print("Start the app with: .venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
