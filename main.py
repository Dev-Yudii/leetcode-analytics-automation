"""Entry point of the daily pipeline.

Usage:
    python main.py

Exit codes:
    0  the challenge was collected and everything went fine
    1  nothing was collected (network, layout change or missing identity)
    2  the challenge was collected but a step failed (degraded run)
"""

import sys

from scripts.pipeline import run_daily
from scripts.runlog import RunLogger


def main() -> int:
    # The Windows console is often cp1252: printing a non-ASCII title
    # would raise UnicodeEncodeError and kill the run.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    logger = RunLogger()
    result = run_daily(logger=logger)
    logger.info(f"Run status: {result.status}")
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
