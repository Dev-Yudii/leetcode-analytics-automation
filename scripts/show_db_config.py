"""Show the shape of the database connections.

The credentials never reach the console. This script exists so that a
diagnostic never needs the raw `.env` file: it prints the scheme, the
host, the database, the user and the length of the password — enough to
know which database the pipeline is talking to, and nothing that can be
reused against it.

That is the rule of the project: a credential is never printed, the
diagnostic shows the shape.

Usage:
    uv run python scripts/show_db_config.py
    uv run python scripts/show_db_config.py --check
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# The variables that hold a connection.
CONNECTION_VARS = (
    "LEETCODE_DB_URL",
    "LEETCODE_TEST_DB_URL",
    "LEETCODE_ADMIN_DB_URL",
)

# What each one is for. The admin one is not stored in `.env` on
# purpose: it is a cluster-level credential and the file is read by
# every single run.
PURPOSES = {
    "LEETCODE_DB_URL": "the operational database — the pipeline, the sync and the GitHub secret",
    "LEETCODE_TEST_DB_URL": "the separate database used by the test suite",
    "LEETCODE_ADMIN_DB_URL": "the database owner — only needed to provision a role",
}

# Captured before the `.env` file is loaded. This is what tells the
# difference between a real environment variable and the local file —
# and a real environment variable always wins.
_FROM_ENVIRONMENT = {
    name: os.environ.get(name) for name in CONNECTION_VARS
}

from scripts.db_utils import connection_shape, password_length  # noqa: E402


def _source_of(name: str) -> str:
    """Where the value of the variable comes from."""
    if _FROM_ENVIRONMENT.get(name):
        return "environment variable"
    if os.environ.get(name):
        return ".env file"
    return "not set"


def describe(name: str) -> str:
    """The description of one connection."""
    url = os.environ.get(name) or ""
    lines = [name, f"  purpose  : {PURPOSES.get(name, '')}", f"  source   : {_source_of(name)}"]

    if not url:
        lines.append("  value    : not set")
        return "\n".join(lines)

    lines.append(f"  shape    : {connection_shape(url)}")
    lines.append(f"  password : {password_length(url)} characters (hidden)")
    return "\n".join(lines)


def check() -> int:
    """Open the operational connection and report what it is."""
    import psycopg

    from scripts.db_utils import get_db_url

    url = get_db_url()

    try:
        with psycopg.connect(url, connect_timeout=10) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT current_user, current_database()")
                user, database = cursor.fetchone()
                cursor.execute("SHOW server_version")
                version = cursor.fetchone()[0]
    except Exception as e:
        from scripts.redact import redact

        print(f"  could not connect: {redact(e)}")
        return 1

    print(f"  connected as : {user}")
    print(f"  database     : {database}")
    print(f"  server       : PostgreSQL {version}")
    return 0


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Show the shape of the database connections (never the secret)"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="also open the operational connection and report who it is",
    )
    args = parser.parse_args(argv)

    print("Database connections — the credentials are never printed")
    print()

    for name in CONNECTION_VARS:
        print(describe(name))
        print()

    if args.check:
        print("Connectivity check (LEETCODE_DB_URL)")
        return check()

    print(
        "The GitHub Actions secret LEETCODE_DB_URL must hold the same value"
        " as the local LEETCODE_DB_URL."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
