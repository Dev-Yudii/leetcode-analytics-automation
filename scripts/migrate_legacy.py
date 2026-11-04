"""Migrate the legacy SQLite database into PostgreSQL.

The old table kept only the first topic of each problem, in a `category`
column. The complete topic list of every collected problem still lives in
the generated files, so the migration reads the files as well and rebuilds
the full relationship (docs/architecture.md, sections 9, 11 and 21).

The topic IDs come from the versioned catalog `data/topics.json`: the
database never invents an identity of its own (§12, §15).

Usage:
    python scripts/migrate_legacy.py [--dry-run]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.export_legacy import read_legacy_rows
from scripts.paths import get_legacy_db_path, get_output_path
from scripts.persistence import (
    ENRICHED,
    INSERTED,
    UNCHANGED,
    link_problem_topics,
    sync_topics,
    upsert_problem,
)
from scripts.topics import get_or_create_topic_id, normalize_topic_name


def find_generated_file(problem_id: str, output_path: Path) -> Path | None:
    """Find the generated file of a problem inside the output folder."""
    matches = sorted(output_path.glob(f"*/{problem_id}_*.py"))
    return matches[0] if matches else None


def read_tags(file_path: Path) -> list[str]:
    """Read the topic names from the header of a generated file."""
    lines = file_path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "Tags:":
            for candidate in lines[index + 1:]:
                value = candidate.strip()
                if value:
                    return [tag.strip() for tag in value.split(",") if tag.strip()]
            return []
    return []


def relative_path(file_path: Path, output_path: Path) -> str:
    """Path of the file relative to the output folder (never absolute)."""
    try:
        return file_path.relative_to(output_path).as_posix()
    except ValueError:
        return file_path.name


def migrate(dry_run: bool = False) -> int:
    db_path = get_legacy_db_path()
    output_path = get_output_path()
    rows = read_legacy_rows(db_path)

    print(f"Legacy database: {db_path}")
    print(f"Output folder:   {output_path}")
    print(f"Rows to migrate: {len(rows)}")
    if dry_run:
        print("Dry run: nothing was written.")
        return 0

    migrated = 0
    for row in rows:
        problem_id = row["id"]
        generated = find_generated_file(problem_id, output_path)
        tags = read_tags(generated) if generated else []

        topic_ids = {}
        for tag in tags:
            normalized = normalize_topic_name(tag)
            topic_ids[normalized] = get_or_create_topic_id(tag)

        file_path = relative_path(generated, output_path) if generated else f"general/{problem_id}.py"
        data = {
            "id": problem_id,
            "title": row["title"],
            "slug": row["slug"],
            "link": row["link"],
            "difficulty": row["difficulty"],
            "date": row["date_generated"],
        }

        outcome = upsert_problem(data, file_path=file_path, status=row["status"] or "PENDING")
        sync_topics(topic_ids)
        linked = link_problem_topics(problem_id, topic_ids)

        migrated += 1
        marker = {INSERTED: "+", ENRICHED: "~", UNCHANGED: "="}[outcome]
        print(f"{marker} {problem_id:>5}  {file_path:<55} topics={linked}")

    print(f"\nProblems migrated: {migrated}")
    return 0


if __name__ == "__main__":
    sys.exit(migrate(dry_run="--dry-run" in sys.argv))
