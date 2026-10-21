"""Persistence of collected problems.

Only storage lives here: no file generation, no HTTP, no catalog writes.
The pipeline decides the order of the steps (docs/architecture.md, section 17)
and this module is called before the file is generated, so a problem is
never lost because a file already exists.
"""

import sqlite3

from scripts.db_utils import connect
from scripts.topics import folder_name_for_topic

TABLE_NAME = "leetcode_problems"

CREATE_TABLE_QUERY = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        id TEXT PRIMARY KEY,
        title TEXT,
        slug TEXT,
        link TEXT,
        difficulty TEXT,
        date_generated TEXT,
        category TEXT,
        status TEXT DEFAULT 'PENDING'
    )
"""

# Legacy schema, kept as is until the PostgreSQL migration (Pass 2).
# `date_generated` holds the challenge date and `category` holds the first
# topic: both are replaced by `challenge_date` and by the `problem_topics`
# table in the new model.
COLUMNS = ("id", "title", "slug", "link", "difficulty", "date_generated", "category")

INSERTED = "inserted"
ENRICHED = "enriched"
UNCHANGED = "unchanged"


class PersistenceError(Exception):
    """The problem could not be stored. The message states the real cause."""


def _row_values(data: dict) -> dict:
    """Map the collected challenge onto the legacy table columns."""
    topics = data.get("topics") or []
    category = folder_name_for_topic(topics[0]).upper() if topics else ""
    return {
        "id": data.get("id"),
        "title": data.get("title"),
        "slug": data.get("slug"),
        "link": data.get("link"),
        "difficulty": data.get("difficulty"),
        "date_generated": data.get("date"),
        "category": category,
    }


def _is_empty(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def ensure_schema(db_path=None) -> None:
    """Create the problems table when it does not exist yet."""
    conn = None
    try:
        conn = connect(db_path)
        conn.execute(CREATE_TABLE_QUERY)
        conn.commit()
    except sqlite3.IntegrityError as e:
        if conn:
            conn.rollback()
        raise PersistenceError(f"could not create the table '{TABLE_NAME}': {e}") from e
    except sqlite3.OperationalError as e:
        if conn:
            conn.rollback()
        raise PersistenceError(
            f"could not open the database to create the table '{TABLE_NAME}': {e}"
        ) from e
    except sqlite3.DatabaseError as e:
        if conn:
            conn.rollback()
        raise PersistenceError(f"the database file is corrupted: {e}") from e
    except OSError as e:
        if conn:
            conn.rollback()
        raise PersistenceError(f"no permission to write the database file: {e}") from e
    finally:
        if conn:
            conn.close()


def upsert_problem(data: dict, db_path=None) -> str:
    """Store the collected problem.

    Returns INSERTED, ENRICHED or UNCHANGED.

    Re-running the pipeline never creates a duplicate logical record
    (architecture section 18) and never overwrites a value that was already
    collected: only fields that are still empty are filled in (section 20).
    """
    values = _row_values(data)
    problem_id = values["id"]
    if not problem_id:
        raise PersistenceError("the problem has no identity (questionFrontendId missing)")

    ensure_schema(db_path)

    conn = None
    try:
        conn = connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {', '.join(COLUMNS)} FROM {TABLE_NAME} WHERE id = ?", (problem_id,)
        )
        existing = cursor.fetchone()
        cursor.close()

        if existing is None:
            placeholders = ", ".join("?" for _ in COLUMNS)
            conn.execute(
                f"INSERT INTO {TABLE_NAME} ({', '.join(COLUMNS)}) VALUES ({placeholders})",
                tuple(values[column] for column in COLUMNS),
            )
            conn.commit()
            return INSERTED

        stored = dict(zip(COLUMNS, existing))
        updates = {
            column: values[column]
            for column in COLUMNS
            if column != "id" and _is_empty(stored.get(column)) and not _is_empty(values[column])
        }
        if not updates:
            conn.commit()
            return UNCHANGED

        assignments = ", ".join(f"{column} = ?" for column in updates)
        conn.execute(
            f"UPDATE {TABLE_NAME} SET {assignments} WHERE id = ?",
            tuple(updates.values()) + (problem_id,),
        )
        conn.commit()
        return ENRICHED

    except sqlite3.IntegrityError as e:
        if conn:
            conn.rollback()
        raise PersistenceError(f"the problem {problem_id} is already registered: {e}") from e
    except sqlite3.OperationalError as e:
        if conn:
            conn.rollback()
        raise PersistenceError(
            f"could not write to the database (locked, missing or read-only): {e}"
        ) from e
    except sqlite3.DatabaseError as e:
        if conn:
            conn.rollback()
        raise PersistenceError(f"the database file is corrupted: {e}") from e
    except OSError as e:
        if conn:
            conn.rollback()
        raise PersistenceError(f"no permission to write the database file: {e}") from e
    finally:
        if conn:
            conn.close()
