"""Export the legacy SQLite database to CSV.

The old database is replaced by PostgreSQL (docs/architecture.md, section 21).
This script keeps a readable copy of the 18 problems collected so far, so
nothing is lost when the legacy file is left behind.

Usage:
    python scripts/export_legacy.py
"""

import csv
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.paths import get_archive_dir, get_legacy_db_path

COLUMNS = ("id", "title", "slug", "link", "difficulty", "date_generated", "category", "status")


def read_legacy_rows(db_path: Path) -> list[dict]:
    """Read every row of the legacy table."""
    if not db_path.exists():
        raise FileNotFoundError(f"legacy database not found: {db_path}")

    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT id, title, slug, link, difficulty, date_generated, category, status"
                " FROM leetcode_problems ORDER BY date_generated"
            ).fetchall()
        except sqlite3.OperationalError as e:
            raise RuntimeError(f"the legacy table could not be read: {e}") from e
    return [dict(row) for row in rows]


def export(rows: list[dict], target: Path) -> Path:
    """Write the rows to a CSV file."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column) for column in COLUMNS})
    return target


def main() -> int:
    db_path = get_legacy_db_path()
    rows = read_legacy_rows(db_path)

    stamp = datetime.now().strftime("%Y-%m-%d")
    target = get_archive_dir() / f"leetcode_problems_legacy_{stamp}.csv"
    export(rows, target)

    print(f"Legacy database: {db_path}")
    print(f"Rows exported:   {len(rows)}")
    print(f"Archive:         {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
