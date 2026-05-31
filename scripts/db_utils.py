import sqlite3
from pathlib import Path

# Discover where this script is located (project/scripts)
CURRENT_DIR = Path(__file__).resolve().parent

# Go up three levels to reach the root workspace directory (C:\Developer)
USER_DIR = CURRENT_DIR.parents[2]

# Path where problem-solving repository lives
OUTPUT_BASE_PATH = USER_DIR/"Problem-Solving"/"LeetCode"

# Target the exact database file inside that folder
DB_PATH = OUTPUT_BASE_PATH/"leetcode_history.db"


def execute_query(query: str, params: tuple = ()) -> list:
    """
    A generic utility to execute ANY SQL query.
    Handles connections, transactions, errors, and resource cleanup.
    """
    # Standard database connection setup
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    result = []

    try:
        # Executing the query using parameterized inputs to prevent SQL Injection
        cursor.execute(query, params)
        
        # If it is a data retrieval operation (SELECT), fetch the rows
        if query.strip().upper().startswith("SELECT"):
            result = cursor.fetchall()
        else:
            # For write operations (INSERT, UPDATE, DELETE), commit the changes
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