import os
import sqlite3
from pathlib import Path

# Discover where this script is located (project/scripts)
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent

# Default workspace layout: <user>/Projects/<project> -> <user>/Problem-Solving/LeetCode
DEFAULT_USER_DIR = PROJECT_ROOT.parents[1]
DEFAULT_OUTPUT_PATH = DEFAULT_USER_DIR / "Problem-Solving" / "LeetCode"

OUTPUT_DIR_ENV = "LEETCODE_OUTPUT_DIR"
DB_PATH_ENV = "LEETCODE_DB_PATH"


def get_output_path() -> Path:
    """Folder where the solution files and the database live.

    Overridable with the LEETCODE_OUTPUT_DIR environment variable so the
    project does not depend on a fixed folder layout.
    """
    override = os.environ.get(OUTPUT_DIR_ENV)
    return Path(override) if override else DEFAULT_OUTPUT_PATH


def get_db_path() -> Path:
    """Path of the local SQLite database.

    Overridable with the LEETCODE_DB_PATH environment variable.
    """
    override = os.environ.get(DB_PATH_ENV)
    return Path(override) if override else get_output_path() / "leetcode_history.db"


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a connection to the local database, creating the folder if needed."""
    path = Path(db_path) if db_path else get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(path))


def execute_query(query: str, params: tuple = (), db_path: Path | None = None) -> list:
    """
    A generic utility to execute ANY SQL query.
    Handles connections, transactions, errors, and resource cleanup.
    """
    # Standard database connection setup
    conn = connect(db_path)
    cursor = conn.cursor()
    result = []

    try:
        # Executing the query using parameterized inputs to prevent SQL Injection
        cursor.execute(query, params)

        # A query that returns rows is a SELECT: fetch them. Anything else
        # is a write: commit the change.
        if cursor.description is not None:
            result = cursor.fetchall()
        else:
            conn.commit()
            print(f"[DB SUCCESS] Rows affected: {cursor.rowcount}")

        return result

    except Exception as e:
        # Rollback changes if anything breaks to avoid data corruption
        conn.rollback()
        print(f"[DB ERROR] Operation failed. Details: {e}")
        raise e
    finally:
        # Guaranteeing resources are closed no matter what
        cursor.close()
        conn.close()


    """
    # Write any query here to test or run maintenance (e.g., updating all to SOLVED)
    my_query = "
        UPDATE leetcode_problems
        SET status = 'SOLVED'
        WHERE status = ?
    "
    variables = ("PENDING",)
    """
if __name__ == "__main__":
    print("LeetCode Database modifier")

    # Write ANY query here (ALTER, SELECT, UPDATE, DELETE) to run it
    my_query = """
        ALTER TABLE leetcode_problems ADD COLUMN memory_mb REAL;
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
        print(f"\n[ERROR] Operation failed. Details: {e}")


"""
    # TEMPLATE A: Add new columns Run these one by one if needed
    my_query = "ALTER TABLE leetcode_problems ADD COLUMN start_time TEXT;"
    my_query = "ALTER TABLE leetcode_problems ADD COLUMN time_spent_minutes INTEGER;"
    variables = ()

    # TEMPLATE B: Update row values
    my_query = ""
        UPDATE leetcode_problems
        SET status = ?
        WHERE id = ?
    ""
    variables = ("SOLVED", "2126")

    # TEMPLATE C: Select and view data
    my_query = ""
        SELECT id, title, category, status
        FROM leetcode_problems
        WHERE category = ?
    ""
    variables = ("ARRAY",)

    # TEMPLATE D: Delete rows
    my_query = ""
        DELETE FROM leetcode_problems
        WHERE id = ?
    ""
    variables = ("2126",)
"""
