"""Persistence of collected problems in PostgreSQL.

Only storage lives here: no file generation, no HTTP, no catalog writes.
The pipeline decides the order of the steps (docs/architecture.md, section 17)
and this module is called before the file is generated, so a problem is
never lost because a file already exists.
"""

import psycopg

from scripts.db_utils import apply_schema, get_connection

INSERTED = "inserted"
ENRICHED = "enriched"
UNCHANGED = "unchanged"

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
                        " (id, title, slug, link, difficulty, challenge_date, file_path, status)"
                        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
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
