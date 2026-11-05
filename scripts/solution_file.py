"""The convention that marks a generated file as solved.

The template tells the user to add a line reading "# Solved" at the end of
the file. The sync reads that line to know when a challenge is finished.

The solution is not stored next to the template: the template is replaced
by the resolution, in the same file. The git history keeps both versions.
"""

import re
from pathlib import Path

# Matches "# Solved", "#solved", "# --solved" and "# SOLVED" on a line of
# its own. The hint line written by the generator does not match it.
SOLVED_MARKER = re.compile(r"^#\s*-{0,2}\s*solved\s*$", re.IGNORECASE | re.MULTILINE)

SOLVED_INSTRUCTION = (
    '# Add a line reading "# Solved" below when you finish the solution.'
)

NOTES_PLACEHOLDER = "    - Type your approach, insights and learnings here."


def is_solved(path) -> bool:
    """True when the file carries the solved marker."""
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return bool(SOLVED_MARKER.search(content))


def problem_id_from_path(path) -> str | None:
    """Read the LeetCode problem ID from a solution file name.

    The generator names the file "{id}_{slug}.py" and the ID is the identity
    used by the database.
    """
    stem = Path(path).stem
    head = stem.split("_", 1)[0]
    return head if head.isdigit() else None
