"""Create a consistent SQLite backup in data/backups.

Usage:
    python scripts/backup_db.py
    python scripts/backup_db.py --include-key

The database backup contains encrypted API credentials. The encryption key at
data/.secret_key is separate; without it, stored credentials cannot be
decrypted on another machine. ``--include-key`` copies the key next to the
backup for disaster recovery; store that folder securely.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import DATA_DIR, settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up the RedditPilot SQLite database.")
    parser.add_argument(
        "--include-key",
        action="store_true",
        help="Also copy data/.secret_key next to the backup. Keep the result secure.",
    )
    parser.add_argument("--output", help="Optional explicit output file path.")
    args = parser.parse_args()

    if not settings.database_url.startswith("sqlite"):
        print("This script only supports SQLite. Use your database server's backup tool.")
        return 2

    raw = settings.database_url.replace("sqlite:///", "", 1)
    source_path = Path(raw)
    if not source_path.is_absolute():
        source_path = ROOT / source_path
    if not source_path.exists():
        print(f"Database not found: {source_path}")
        return 1

    backups = DATA_DIR / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = Path(args.output) if args.output else backups / f"redditpilot-backup-{stamp}.db"
    target.parent.mkdir(parents=True, exist_ok=True)

    source = sqlite3.connect(str(source_path))
    destination = sqlite3.connect(str(target))
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()

    print(f"Backup written to {target}")
    if args.include_key:
        key_source = settings.secret_key_file
        if not key_source.exists():
            print("No local key file found; APP_SECRET_KEY may be set in .env instead.")
        else:
            key_target = target.with_name(target.name + ".secret_key")
            shutil.copy2(key_source, key_target)
            print(f"Encryption key copied to {key_target}")
            print("Store the backup and key securely; together they expose saved credentials.")
    else:
        print("Remember: data/.secret_key (or APP_SECRET_KEY) is required to decrypt saved credentials.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
