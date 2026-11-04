"""Entry point of the daily pipeline.

Usage:
    python main.py
    python main.py --backfill
    python main.py --backfill --since 2026-10-01 --until 2026-10-31

Exit codes:
    0  the challenge was collected and everything went fine
    1  nothing was collected (network, layout change or missing identity)
    2  the challenge was collected but a step failed (degraded run)
"""

import argparse
import sys

from scripts.backfill import run_backfill
from scripts.pipeline import run_daily
from scripts.runlog import RunLogger


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LeetCode Daily Challenge pipeline")
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="recover Daily Challenges missing from the database",
    )
    parser.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        help="first date to check when using --backfill (default: 60-day lookback)",
    )
    parser.add_argument(
        "--until",
        metavar="YYYY-MM-DD",
        help="last date to check when using --backfill (default: yesterday UTC)",
    )
    return parser


def main(argv=None) -> int:
    # The Windows console is often cp1252: printing a non-ASCII title
    # would raise UnicodeEncodeError and kill the run.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.backfill and (args.since or args.until):
        parser.error("--since and --until require --backfill")

    logger = RunLogger()

    if args.backfill:
        try:
            result = run_backfill(logger=logger, since=args.since, until=args.until)
        except Exception as e:
            logger.error(f"Backfill failed: {e!r}")
            return 1
        logger.info(f"Backfill status: {result.status}")
        return result.exit_code

    result = run_daily(logger=logger)
    logger.info(f"Run status: {result.status}")
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
