"""Recover Daily Challenges that were missed.

The normal pipeline only knows today's challenge. This module walks the
monthly history exposed by LeetCode, compares it with the `daily_challenges`
ledger and replays the normal pipeline for every missing date. It is the
safety net for a failed scheduled run, a database outage or a trip with the
computer turned off.
"""

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from scripts.leetcode_client import get_challenge_for_record, list_daily_challenges
from scripts.persistence import get_covered_dates, seed_daily_challenges
from scripts.pipeline import (
    DEGRADED,
    EXIT_DEGRADED,
    EXIT_FATAL,
    EXIT_OK,
    FAILED,
    OK,
    run_daily,
)

# The daily scheduled run checks this many days back. It is intentionally
# larger than a month so a short trip and the month boundary are covered.
DEFAULT_LOOKBACK_DAYS = int(os.environ.get("LEETCODE_BACKFILL_DAYS", "60"))


class BackfillError(Exception):
    """The backfill cannot start or its arguments are invalid."""


@dataclass
class BackfillResult:
    """What happened while recovering a range of dates."""

    since: date
    until: date
    missing: list[date] = field(default_factory=list)
    collected: list[date] = field(default_factory=list)
    skipped: list[date] = field(default_factory=list)
    failed: list[tuple[date, str]] = field(default_factory=list)
    status: str = OK
    exit_code: int = EXIT_OK


class LeetCodeSource:
    """Thin adapter so tests can replace the network with fixtures."""

    def list_month(self, year: int, month: int) -> list[dict]:
        return list_daily_challenges(year, month)

    def get_challenge(self, record: dict) -> dict:
        return get_challenge_for_record(record)


def _as_date(value, name: str) -> date | None:
    if value is None or isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise BackfillError(f"Invalid {name} {value!r}; expected YYYY-MM-DD")
    raise BackfillError(f"Invalid {name} {value!r}; expected YYYY-MM-DD")


def _date_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def find_missing_dates(since: date, until: date) -> list[date]:
    """Dates in the range without a row in `daily_challenges`."""
    covered = get_covered_dates(since, until)
    return [day for day in _date_range(since, until) if day.isoformat() not in covered]


def run_backfill(
    logger=None,
    since=None,
    until=None,
    source=None,
    runner=None,
) -> BackfillResult:
    """Recover every missing Daily Challenge in the requested range.

    `since` defaults to a lookback window ending at `until` (yesterday UTC
    by default). A full historical recovery must pass `since` explicitly.
    """
    if logger is None:
        from scripts.runlog import RunLogger

        logger = RunLogger()
    source = source or LeetCodeSource()
    runner = runner or run_daily

    parsed_until = _as_date(until, "until")
    if parsed_until is None:
        parsed_until = datetime.now(timezone.utc).date() - timedelta(days=1)

    parsed_since = _as_date(since, "since")
    if parsed_since is None:
        parsed_since = parsed_until - timedelta(days=DEFAULT_LOOKBACK_DAYS)
        logger.info(
            f"No --since given; checking the last {DEFAULT_LOOKBACK_DAYS} days"
            f" ({parsed_since} to {parsed_until})"
        )

    result = BackfillResult(since=parsed_since, until=parsed_until)
    if parsed_since > parsed_until:
        logger.info(f"Backfill: nothing to check ({parsed_since} > {parsed_until})")
        return result

    try:
        seed_daily_challenges()
    except Exception as e:
        raise BackfillError(f"could not prepare the occurrence ledger: {e}") from e

    result.missing = find_missing_dates(parsed_since, parsed_until)
    if not result.missing:
        logger.info(f"Backfill: no gaps between {parsed_since} and {parsed_until}")
        return result

    logger.info(
        f"Backfill: {len(result.missing)} missing day(s) between"
        f" {parsed_since} and {parsed_until}"
    )

    by_month: dict[tuple[int, int], list[date]] = {}
    for day in result.missing:
        by_month.setdefault((day.year, day.month), []).append(day)

    for (year, month), days in sorted(by_month.items()):
        try:
            records = source.list_month(year, month)
        except Exception as e:
            message = f"could not list {year}-{month:02d}: {e}"
            logger.error(f"Backfill: {message}")
            result.failed.extend((day, message) for day in days)
            continue

        by_date = {
            record.get("date"): record
            for record in records
            if isinstance(record, dict) and isinstance(record.get("date"), str)
        }

        for day in sorted(days):
            record = by_date.get(day.isoformat())
            if record is None:
                logger.warning(f"Backfill: LeetCode has no challenge for {day.isoformat()}")
                result.skipped.append(day)
                continue

            try:
                data = source.get_challenge(record)
            except Exception as e:
                logger.error(f"Backfill: could not collect {day.isoformat()}: {e}")
                result.failed.append((day, str(e)))
                continue

            try:
                outcome = runner(logger=logger, collector=lambda: data)
            except Exception as e:
                logger.error(f"Backfill: pipeline failed for {day.isoformat()}: {e!r}")
                result.failed.append((day, repr(e)))
                continue

            if outcome.status == OK:
                logger.info(f"Backfill: collected {day.isoformat()}")
                result.collected.append(day)
            else:
                detail = "; ".join(
                    f"{step.name}={step.status}: {step.detail}"
                    for step in outcome.steps
                    if step.status != OK
                )
                logger.error(f"Backfill: {day.isoformat()} ended {outcome.status}: {detail}")
                result.failed.append((day, f"{outcome.status}: {detail}"))

    if result.failed:
        result.status = FAILED if not result.collected else DEGRADED
    elif result.skipped:
        result.status = DEGRADED
    else:
        result.status = OK

    result.exit_code = {
        OK: EXIT_OK,
        DEGRADED: EXIT_DEGRADED,
    }.get(result.status, EXIT_FATAL)

    logger.info(
        f"Backfill summary: {len(result.collected)} collected,"
        f" {len(result.failed)} failed, {len(result.skipped)} skipped"
    )
    return result
