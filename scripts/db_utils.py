"""Database engine: connection, generic query execution and the schema.

The operational database is PostgreSQL (docs/architecture.md, section 21).
The connection is configured with environment variables so the same code
runs locally, in Docker and in GitHub Actions.
"""

import os
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = PROJECT_ROOT / "db" / "schema.sql"

DB_URL_ENV = "LEETCODE_DB_URL"
DEFAULT_DB_URL = "postgresql://leetcode:leetcode_local_dev@localhost:5432/leetcode_analytics"

# A scheduler must not wait forever for a database that is not answering.
CONNECT_TIMEOUT = int(os.environ.get("LEETCODE_DB_TIMEOUT", "10"))

# The local .env file holds the credentials for the notebook. It never
# overrides a real environment variable, so the GitHub Actions secret
# always wins in CI. The file is gitignored and never committed.
load_dotenv()


def get_db_url() -> str:
    """Connection string of the operational database."""
    return os.environ.get(DB_URL_ENV, DEFAULT_DB_URL)


def connection_shape(url: str) -> str:
    """The connection without the secret, for the console.

    The shape answers the question a diagnostic really asks — which
    server, which database, which user — and it cannot be reused
    against the server. The password appears only as its length.
    """
    parts = urlsplit(url or "")

    scheme = parts.scheme or "?"
    user = parts.username or ""
    host = parts.hostname or "?"
    port = f":{parts.port}" if parts.port else ""
    database = parts.path or "/"
    query = f"?{parts.query}" if parts.query else ""

    return f"{scheme}://{user}:***@{host}{port}{database}{query}"


def password_length(url: str) -> int:
    """How many characters the password of the connection has."""
    parts = urlsplit(url or "")
    return len(parts.password or "")


def get_connection() -> psycopg.Connection:
    """Open a connection to PostgreSQL."""
    return psycopg.connect(get_db_url(), connect_timeout=CONNECT_TIMEOUT)


def execute_query(query: str, params: tuple = ()) -> list[dict]:
    """
    A generic utility to execute ANY SQL query.
    Handles connections, transactions, errors, and resource cleanup.
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, params)

            # A query that returns rows is a SELECT: fetch them. Anything
            # else is a write: the context manager commits it.
            if cursor.description is not None:
                return cursor.fetchall()
            return []


def apply_schema() -> None:
    """Create the tables when they do not exist yet (idempotent)."""
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(schema)


if __name__ == "__main__":
    print("LeetCode Database modifier")

    # Write ANY query here (ALTER, SELECT, UPDATE, DELETE) to run it
    my_query = """
        SELECT id, title, difficulty, status
        FROM problems
        ORDER BY challenge_date DESC
    """
    variables = ()

    try:
        print(f"Executing operation...")
        rows = execute_query(my_query, variables)

        # If the query returned data (like a SELECT statement), display the rows
        if rows:
            print("\n>>> Query Results:")
            for row in rows:
                print(row)
        else:
            print(">>> Success! Database modified, no rows returned.")

    except Exception as e:
        # The message of a driver error can carry the connection
        # string: it is redacted before it reaches the console.
        from scripts.redact import redact

        print(f"\n[ERROR] Operation failed. Details: {redact(e)}")


"""
    # TEMPLATE A: Add new columns Run these one by one if needed
    my_query = "ALTER TABLE problems ADD COLUMN beats TEXT;"
    variables = ()

    # TEMPLATE B: Update row values
    my_query = ""
        UPDATE problems
        SET status = %s
        WHERE id = %s
    ""
    variables = ("CONCLUDED", "3863")

    # TEMPLATE C: Select and view data
    my_query = ""
        SELECT p.id, p.title, t.name AS topic
        FROM problems p
        JOIN problem_topics pt ON pt.problem_id = p.id
        JOIN topics t ON t.id = pt.topic_id
        WHERE t.name = %s
        ORDER BY p.challenge_date
    ""
    variables = ("String",)

    # TEMPLATE D: Delete rows
    my_query = ""
        DELETE FROM problems
        WHERE id = %s
    ""
    variables = ("3863",)
"""
