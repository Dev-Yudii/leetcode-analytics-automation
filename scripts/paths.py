"""Where the project reads and writes.

The output folder and the paths are configurable with environment
variables, so the project does not depend on a fixed folder layout and
can run locally or in GitHub Actions without changes.
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Default workspace layout: <user>/Projects/<project> -> <user>/Problem-Solving/LeetCode
DEFAULT_USER_DIR = PROJECT_ROOT.parents[1]
DEFAULT_OUTPUT_PATH = DEFAULT_USER_DIR / "Problem-Solving" / "LeetCode"

OUTPUT_DIR_ENV = "LEETCODE_OUTPUT_DIR"
LEGACY_DB_ENV = "LEETCODE_LEGACY_DB"

LEGACY_DB_NAME = "leetcode_history.db"
ARCHIVE_DIR = PROJECT_ROOT / "data" / "archive"


def get_output_path() -> Path:
    """Folder where the solution files live."""
    override = os.environ.get(OUTPUT_DIR_ENV)
    return Path(override) if override else DEFAULT_OUTPUT_PATH


def get_legacy_db_path() -> Path:
    """Path of the old SQLite database (read only, kept as an archive)."""
    override = os.environ.get(LEGACY_DB_ENV)
    if override:
        return Path(override)
    return get_output_path() / LEGACY_DB_NAME


def get_archive_dir() -> Path:
    """Folder where the exports of the legacy database are archived."""
    return ARCHIVE_DIR
