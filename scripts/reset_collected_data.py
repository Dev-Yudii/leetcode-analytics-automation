"""Reset the collected data, keeping one day.

The pipeline was restarted on 2026-11-05: the collected data was reset so
the ledger starts from the new daily challenge and the notebook holds one
open challenge instead of a backlog.

The topic catalog in data/topics.json is the identity ledger and is never
touched: the topic IDs stay stable and are never reused, the `topics` table
is simply rebuilt from the challenges that are collected from now on.

Usage:
    uv run python scripts/reset_collected_data.py --date 2026-11-05
    uv run python scripts/reset_collected_data.py --date 2026-11-05 --dry-run
"""

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.db_utils import get_connection
from scripts.persistence import ensure_schema


class ResetError(Exception):
    """The reset could not run. The message states the real cause."""


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise ResetError(f"invalid date {value!r}; expected YYYY-MM-DD") from e


def preview(keep_date: date) -> dict:
    """Count what the reset would remove."""
    ensure_schema()

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM problems"
                " WHERE id NOT IN (SELECT problem_id FROM daily_challenges"
                "                   WHERE challenge_date = %s)",
                (keep_date,),
            )
            problems = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM daily_challenges WHERE challenge_date <> %s",
                (keep_date,),
            )
            occurrences = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM problems"
                " WHERE id IN (SELECT problem_id FROM daily_challenges"
                "              WHERE challenge_date = %s)",
                (keep_date,),
            )
            kept = cursor.fetchone()[0]

    return {
        "kept": kept,
        "problems_to_delete": problems,
        "occurrences_to_delete": occurrences,
    }


def reset(keep_date: date, dry_run: bool = False) -> dict:
    """Remove every collected day except the given one."""
    ensure_schema()

    if dry_run:
        return preview(keep_date)

    removed = {}
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "CREATE TEMP TABLE _keep AS"
                " SELECT problem_id AS id FROM daily_challenges"
                " WHERE challenge_date = %s",
                (keep_date,),
            )

            # A problem collected before the `generated_at` column existed
            # has it empty. The collection run knows when the challenge was
            # extracted, so the timestamp is recovered from there before
            # the runs are pruned.
            cursor.execute(
                "UPDATE problems p"
                " SET generated_at = COALESCE(p.generated_at, r.started_at)"
                " FROM collection_runs r"
                " WHERE r.problem_id = p.id"
                "   AND p.id IN (SELECT id FROM _keep)"
                "   AND p.generated_at IS NULL"
            )
            removed["generated_at_backfilled"] = cursor.rowcount

            cursor.execute(
                "DELETE FROM collection_events WHERE run_id NOT IN"
                " (SELECT id FROM collection_runs"
                "  WHERE problem_id IN (SELECT id FROM _keep))"
            )
            removed["events"] = cursor.rowcount

            cursor.execute(
                "DELETE FROM collection_runs WHERE id NOT IN"
                " (SELECT id FROM collection_runs"
                "  WHERE problem_id IN (SELECT id FROM _keep))"
            )
            removed["runs"] = cursor.rowcount

            cursor.execute(
                "DELETE FROM daily_challenges WHERE challenge_date <> %s", (keep_date,)
            )
            removed["occurrences"] = cursor.rowcount

            cursor.execute(
                "DELETE FROM problem_topics WHERE problem_id NOT IN (SELECT id FROM _keep)"
            )
            removed["problem_topics"] = cursor.rowcount

            cursor.execute("DELETE FROM problems WHERE id NOT IN (SELECT id FROM _keep)")
            removed["problems"] = cursor.rowcount

            cursor.execute(
                "DELETE FROM topics WHERE id NOT IN (SELECT topic_id FROM problem_topics)"
            )
            removed["topics"] = cursor.rowcount

            cursor.execute("DROP TABLE _keep")

        conn.commit()

    report = preview(keep_date)
    report["removed"] = removed
    report["problems_to_delete"] = removed["problems"]
    report["occurrences_to_delete"] = removed["occurrences"]
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Reset the collected data, keeping one day"
    )
    parser.add_argument(
        "--date",
        default=datetime.now(timezone.utc).date().isoformat(),
        help="the day to keep (YYYY-MM-DD); default: today UTC",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be removed without changing anything",
    )
    args = parser.parse_args(argv)

    try:
        keep_date = _parse_date(args.date)
        report = reset(keep_date, dry_run=args.dry_run)
    except ResetError as e:
        print(f"[ERROR] {e}")
        return 1
    except Exception as e:
        print(f"[ERROR] the reset failed: {e!r}")
        return 1

    prefix = "[dry-run] " if args.dry_run else ""
    print(
        f"{prefix}Kept {report['kept']} problem(s) from {keep_date};"
        f" removed {report['problems_to_delete']} problem(s) and"
        f" {report['occurrences_to_delete']} occurrence(s)."
    )
    backfilled = report.get("removed", {}).get("generated_at_backfilled", 0)
    if backfilled:
        print(f"Recovered the generation time of {backfilled} problem(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
