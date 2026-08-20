"""Copy data/jobs.db to data/jobs_backup.db.

Run on a schedule (Windows Task Scheduler) so scores and application
statuses survive even if the working database is ever lost or corrupted.
Uses sqlite3's backup API instead of a plain file copy so it's safe to run
while the database is open elsewhere.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SOURCE = DATA_DIR / "jobs.db"
BACKUP = DATA_DIR / "jobs_backup.db"


def main() -> int:
    if not SOURCE.exists():
        print(f"No database found at {SOURCE} - nothing to back up.")
        return 1

    src = sqlite3.connect(str(SOURCE))
    dst = sqlite3.connect(str(BACKUP))
    with dst:
        src.backup(dst)
    src.close()
    dst.close()

    print(f"Backed up {SOURCE} -> {BACKUP}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
