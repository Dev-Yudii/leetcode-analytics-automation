"""Persistence of collected problems in PostgreSQL.

Only storage lives here: no file generation, no HTTP, no catalog writes.
The pipeline decides the order of the steps (docs/architecture.md, section 17)
and this module is called before the file is generated, so a problem is
never lost because a file already exists.
"""

from datetime import date, datetime, timezone

import psycopg
from psycopg.rows import dict_row

from scripts.db_utils import apply_schema, get_connection

INSERTED = "inserted"
ENRICHED = "enriched"
UNCHANGED = "unchanged"
SKIPPED = "skipped"

# Columns of the problems table that a re-run may complete.
COMPLETABLE_COLUMNS = ("title", "slug", "link", "difficulty", "challenge_date", "file_path")


class PersistenceError(Exception):
    """The problem could not be stored. The message states the real cause."""


def _translate(error: Exception) -> PersistenceError:
    """Turn a driver error into a message that names the real cause."""
    if isinstance(error, psycopg.errors.UniqueViolation):
        return PersistenceError(f"the record already exists: {error}")
    if isinstance(error, psycopg.errors.ForeignKeyViolation):
        return PersistenceError(f"foreign key violation: {error}")
    if isinstance(error, psycopg.errors.CheckViolation):
        return PersistenceError(f"check constraint violated: {error}")
    if isinstance(error, psycopg.errors.InsufficientPrivilege):
        return PersistenceError(f"the database refused the operation: {error}")
    if isinstance(error, psycopg.OperationalError):
        return PersistenceError(f"could not reach the database: {error}")
    if isinstance(error, psycopg.Error):
        return PersistenceError(f"database error: {error}")
    if isinstance(error, OSError):
        return PersistenceError(f"network or file error: {error}")
    return PersistenceError(f"unexpected error: {error!r}")


def _is_empty(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _row_values(data: dict, file_path: str) -> dict:
    """Map the collected challenge onto the problems table."""
    return {
        "id": data.get("id"),
        "title": data.get("title"),
        "slug": data.get("slug"),
        "link": data.get("link"),
        "difficulty": data.get("difficulty"),
        "challenge_date": data.get("date"),
        "file_path": file_path,
    }


def ensure_schema() -> None:
    """Create the tables when they do not exist yet (idempotent)."""
    try:
        apply_schema()
    except Exception as e:
        raise _translate(e) from e


def upsert_problem(data: dict, file_path: str, status: str | None = None) -> str:
    """Store the collected problem.

    Returns INSERTED, ENRICHED or UNCHANGED.

    Re-running the pipeline never creates a duplicate logical record
    (architecture section 18) and never overwrites a value that was already
    collected: only fields that are still empty are filled in (section 20).
    """
    values = _row_values(data, file_path)
    problem_id = values["id"]
    if not problem_id:
        raise PersistenceError("the problem has no identity (questionFrontendId missing)")

    ensure_schema()

    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT title, slug, link, difficulty, challenge_date, file_path"
                    " FROM problems WHERE id = %s",
                    (problem_id,),
                )
                existing = cursor.fetchone()

                if existing is None:
                    cursor.execute(
                        "INSERT INTO problems"
                        " (id, title, slug, link, difficulty, challenge_date, file_path, status, generated_at)"
                        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())",
                        (
                            values["id"],
                            values["title"],
                            values["slug"],
                            values["link"],
                            values["difficulty"],
                            values["challenge_date"],
                            values["file_path"],
                            status or "PENDING",
                        ),
                    )
                    return INSERTED

                stored = dict(zip(COMPLETABLE_COLUMNS, existing))
                updates = {
                    column: values[column]
                    for column in COMPLETABLE_COLUMNS
                    if _is_empty(stored.get(column)) and not _is_empty(values[column])
                }
                if not updates:
                    return UNCHANGED

                assignments = ", ".join(f"{column} = %s" for column in updates)
                cursor.execute(
                    f"UPDATE problems SET {assignments}, updated_at = now() WHERE id = %s",
                    tuple(updates.values()) + (problem_id,),
                )
                return ENRICHED
    except Exception as e:
        raise _translate(e) from e


def set_collected_at(problem_id: str) -> str:
    """Record that the challenge reached the user's notebook.

    The first time the file is seen locally is the moment the challenge was
    collected. The timestamp is written once and never overwritten, so the
    resolution time always starts at the first collection.
    """
    if not problem_id:
        raise PersistenceError("the problem has no identity (questionFrontendId missing)")

    ensure_schema()
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE problems"
                    " SET collected_at = COALESCE(collected_at, now()),"
                    "     in_progress_at = COALESCE(in_progress_at, now()),"
                    "     status = CASE WHEN status = 'PENDING'"
                    "                   THEN 'IN_PROGRESS' ELSE status END,"
                    "     updated_at = now()"
                    " WHERE id = %s",
                    (problem_id,),
                )
                if cursor.rowcount == 0:
                    return SKIPPED
                return "collected"
    except Exception as e:
        raise _translate(e) from e


def mark_solved(problem_id: str, solved_at=None) -> str:
    """Close a challenge: the user marked the file as solved.

    `solved_at` is when the file was last edited, not when this function
    runs: the sync may happen hours after the resolution.
    """
    if not problem_id:
        raise PersistenceError("the problem has no identity (questionFrontendId missing)")

    moment = solved_at or datetime.now(timezone.utc)
    ensure_schema()
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE problems"
                    " SET status = 'CONCLUDED',"
                    "     solved_at = COALESCE(solved_at, %s),"
                    "     collected_at = LEAST(COALESCE(collected_at, %s), %s),"
                    "     in_progress_at = COALESCE(in_progress_at, %s),"
                    "     concluded_at = COALESCE(concluded_at, now()),"
                    "     updated_at = now()"
                    " WHERE id = %s",
                    (moment, moment, moment, moment, problem_id),
                )
                if cursor.rowcount == 0:
                    return SKIPPED
                return "concluded"
    except Exception as e:
        raise _translate(e) from e


def seed_daily_challenges() -> int:
    """Backfill the occurrence ledger from existing problems.

    This is a one-way bootstrap for databases created before the
    `daily_challenges` table existed. It is idempotent, so running it on
    every pipeline start is safe.
    """
    ensure_schema()
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO daily_challenges (challenge_date, problem_id)"
                    " SELECT challenge_date, id FROM problems"
                    " WHERE challenge_date IS NOT NULL"
                    " ON CONFLICT (challenge_date) DO NOTHING"
                )
                return cursor.rowcount
    except Exception as e:
        raise _translate(e) from e


def record_daily_challenge(challenge_date, problem_id: str) -> str:
    """Record which problem was the Daily Challenge on a date.

    The `problems` table keeps one row per problem; this ledger keeps one
    row per occurrence, so a problem reused years later still has its new
    date recorded.
    """
    if not challenge_date or not problem_id:
        return SKIPPED

    ensure_schema()
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT problem_id FROM daily_challenges WHERE challenge_date = %s",
                    (challenge_date,),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    if existing[0] == problem_id:
                        return UNCHANGED
                    raise PersistenceError(
                        f"the Daily Challenge on {challenge_date} is already recorded"
                        f" for problem {existing[0]}, not {problem_id}"
                    )

                cursor.execute(
                    "INSERT INTO daily_challenges (challenge_date, problem_id)"
                    " VALUES (%s, %s) ON CONFLICT (challenge_date) DO NOTHING",
                    (challenge_date, problem_id),
                )
                return INSERTED if cursor.rowcount else UNCHANGED
    except PersistenceError:
        raise
    except Exception as e:
        raise _translate(e) from e


def get_covered_dates(start: date, end: date) -> set[str]:
    """Return the ISO dates that already have a Daily Challenge record."""
    ensure_schema()
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT challenge_date FROM daily_challenges"
                    " WHERE challenge_date BETWEEN %s AND %s",
                    (start, end),
                )
                return {
                    value.isoformat() if hasattr(value, "isoformat") else str(value)
                    for (value,) in cursor.fetchall()
                }
    except Exception as e:
        raise _translate(e) from e


def get_recorded_date_bounds() -> tuple[date | None, date | None]:
    """Return the first and last Daily Challenge dates in the ledger."""
    ensure_schema()
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT MIN(challenge_date), MAX(challenge_date) FROM daily_challenges"
                )
                row = cursor.fetchone()
                if row is None:
                    return None, None
                return row[0], row[1]
    except Exception as e:
        raise _translate(e) from e


def get_problem(problem_id: str) -> dict | None:
    """Read one problem, or None when the ledger does not know it."""
    if not problem_id:
        return None
    ensure_schema()
    try:
        with get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "SELECT id, title, slug, link, difficulty, challenge_date, file_path,"
                    " status, generated_at, collected_at, solved_at"
                    " FROM problems WHERE id = %s",
                    (problem_id,),
                )
                return cursor.fetchone()
    except Exception as e:
        raise _translate(e) from e


def get_open_problems() -> list[dict]:
    """Problems that are not solved yet, with the path of their file.

    The sync uses this to know which challenges the notebook should hold,
    and the index of the open challenges reads the same rows. The topics
    come along in one aggregate, so the index needs a single query.
    """
    ensure_schema()
    try:
        with get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "SELECT p.id, p.title, p.slug, p.difficulty, p.challenge_date,"
                    " p.file_path, p.status,"
                    " p.generated_at, p.collected_at, p.solved_at,"
                    " COALESCE(string_agg(t.name, ', ' ORDER BY t.name), '') AS topics"
                    " FROM problems p"
                    " LEFT JOIN problem_topics pt ON pt.problem_id = p.id"
                    " LEFT JOIN topics t ON t.id = pt.topic_id"
                    " WHERE p.status <> 'CONCLUDED'"
                    " GROUP BY p.id"
                    " ORDER BY p.challenge_date, p.id"
                )
                return cursor.fetchall()
    except Exception as e:
        raise _translate(e) from e


def sync_topics(topic_ids: dict) -> int:
    """Write the topics to the database using the IDs of the versioned catalog.

    The database never generates an ID on its own (§15). A disagreement
    between the catalog and the database is an error, not something to
    repair silently (§13).
    """
    if not topic_ids:
        return 0

    ensure_schema()
    written = 0
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                for name, topic_id in topic_ids.items():
                    cursor.execute("SELECT id, name FROM topics WHERE id = %s", (topic_id,))
                    by_id = cursor.fetchone()
                    if by_id and by_id[1] != name:
                        raise PersistenceError(
                            f"the catalog and the database disagree about topic {name!r}:"
                            f" catalog id {topic_id}, database id {by_id[0]} with name {by_id[1]!r}"
                        )

                    cursor.execute("SELECT id FROM topics WHERE name = %s", (name,))
                    by_name = cursor.fetchone()
                    if by_name and by_name[0] != topic_id:
                        raise PersistenceError(
                            f"the catalog and the database disagree about topic {name!r}:"
                            f" catalog id {topic_id}, database id {by_name[0]}"
                        )

                    cursor.execute(
                        "INSERT INTO topics (id, name) VALUES (%s, %s)"
                        " ON CONFLICT (id) DO NOTHING",
                        (topic_id, name),
                    )
                    written += 1
    except PersistenceError:
        raise
    except Exception as e:
        raise _translate(e) from e
    return written


def link_problem_topics(problem_id: str, topic_ids: dict) -> int:
    """Associate the problem with every topic returned by LeetCode."""
    if not problem_id or not topic_ids:
        return 0

    ensure_schema()
    linked = 0
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                for topic_id in topic_ids.values():
                    cursor.execute(
                        "INSERT INTO problem_topics (problem_id, topic_id) VALUES (%s, %s)"
                        " ON CONFLICT DO NOTHING",
                        (problem_id, topic_id),
                    )
                    linked += cursor.rowcount
    except Exception as e:
        raise _translate(e) from e
    return linked


def start_run() -> int:
    """Open a collection run and return its id."""
    ensure_schema()
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO collection_runs (status) VALUES ('running') RETURNING id"
                )
                return cursor.fetchone()[0]
    except Exception as e:
        raise _translate(e) from e


def add_event(run_id: int, level: str, step: str, message: str) -> None:
    """Record a warning or an error observed during the run (§19)."""
    if not run_id:
        return
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO collection_events (run_id, level, step, message)"
                    " VALUES (%s, %s, %s, %s)",
                    (run_id, level, step, message),
                )
    except Exception:
        # The audit must never break the run
        pass


def finish_run(
    run_id: int,
    status: str,
    problem_id: str | None = None,
    challenge_date: str | None = None,
    exit_code: int | None = None,
    message: str | None = None,
) -> None:
    """Close the collection run with its outcome."""
    if not run_id:
        return
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE collection_runs SET finished_at = now(), status = %s,"
                    " problem_id = %s, challenge_date = %s, exit_code = %s, message = %s"
                    " WHERE id = %s",
                    (status, problem_id, challenge_date, exit_code, message, run_id),
                )
    except Exception:
        pass
