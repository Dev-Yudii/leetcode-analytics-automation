import sqlite3
import os

# Discover where this script is located (project/scripts)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# Go up three levels to reach the root workspace directory (C:\Developer)
USER_DIR = os.path.dirname(os.path.dirname(os.path.dirname(CURRENT_DIR)))

# Path where problem-solving repository lives
OUTPUT_BASE_PATH = os.path.join(USER_DIR, "Problem-Solving", "LeetCode")

# Target the exact database file inside that folder
DB_PATH = os.path.join(OUTPUT_BASE_PATH, "leetcode_history.db")


def execute_query(query: str, params: tuple = ()) -> list:
    """
    A generic utility to execute ANY SQL query.
    Handles connections, transactions, errors, and resource cleanup.
    """
    # Standard database connection setup
    conn = sqlite3.connect(DB_PATH)
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
    print("Running Database Tool")

    my_query = """
        UPDATE problems 
        SET id = '3121' 
        WHERE id = ?
    """
    variables = (3122,)

    # Executing and printing results dynamically
    try:
        rows = execute_query(my_query, variables)
        print("Operation done!")
        
        # If the query returned data (SELECT), print rows
        if rows:
            print("\n--- Query Results ---")
            for row in rows:
                print(row)
        else:
            # If it was a write operation, notify successful modification
            print("No rows returned. Database successfully modified.")
            
    except Exception as e:
        print(f"Could not execute the operation... Error: {e}")