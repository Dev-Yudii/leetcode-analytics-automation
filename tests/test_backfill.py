"""Tests for the recovery of missed Daily Challenges."""

import copy
from datetime import date

import pytest

from scripts.backfill import BackfillError, run_backfill
from scripts.collection import CollectionError
from scripts.db_utils import execute_query
from scripts.pipeline import run_daily

pytestmark = pytest.mark.usefixtures("postgres_url")


class FakeLogger:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(("INFO", message))

    def warning(self, message):
        self.messages.append(("WARN", message))

    def error(self, message):
        self.messages.append(("ERROR", message))


class FakeSource:
    def __init__(self, records, failures=None):
        self.records = records
        self.failures = set(failures or [])
        self.list_calls = []
        self.detail_calls = []

    def list_month(self, year, month):
        self.list_calls.append((year, month))
        prefix = f"{year:04d}-{month:02d}-"
        return [record for record in self.records if record["date"].startswith(prefix)]

    def get_challenge(self, record):
        self.detail_calls.append(record["date"])
        if record["date"] in self.failures:
            raise CollectionError(f"could not fetch {record['date']}")
        return record["data"]


def make_challenge(sample_challenge, day, problem_id, slug):
    data = copy.deepcopy(sample_challenge)
    data["id"] = problem_id
    data["date"] = day
    data["title"] = f"Problem {problem_id}"
    data["slug"] = slug
    data["link"] = f"https://leetcode.com/problems/{slug}/"
    return data


def make_record(data):
    return {
        "date": data["date"],
        "link": f"/problems/{data['slug']}/",
        "question": {"titleSlug": data["slug"]},
        "data": data,
    }


def read_problem_ids():
    return [row["id"] for row in execute_query("SELECT id FROM problems ORDER BY id")]


def read_occurrences():
    return [
        (str(row["challenge_date"]), row["problem_id"])
        for row in execute_query(
            "SELECT challenge_date, problem_id FROM daily_challenges ORDER BY challenge_date"
        )
    ]


class TestBackfill:
    def test_fills_the_gaps_and_skips_dates_already_recorded(
        self, sample_challenge, temp_output_dir, temp_catalog
    ):
        day_20 = make_challenge(sample_challenge, "2026-10-20", "4001", "problem-4001")
        day_21 = make_challenge(sample_challenge, "2026-10-21", "4002", "problem-4002")
        day_22 = make_challenge(sample_challenge, "2026-10-22", "4003", "problem-4003")

        logger = FakeLogger()
        seed = run_daily(logger=logger, collector=lambda: day_20)
        assert seed.status == "ok"

        source = FakeSource([make_record(day_20), make_record(day_21), make_record(day_22)])
        result = run_backfill(
            logger=logger,
            since=date(2026, 10, 20),
            until=date(2026, 10, 22),
            source=source,
        )

        assert result.missing == [date(2026, 10, 21), date(2026, 10, 22)]
        assert result.collected == [date(2026, 10, 21), date(2026, 10, 22)]
        assert result.failed == []
        assert result.exit_code == 0
        assert read_problem_ids() == ["4001", "4002", "4003"]
        assert read_occurrences() == [
            ("2026-10-20", "4001"),
            ("2026-10-21", "4002"),
            ("2026-10-22", "4003"),
        ]
        assert (temp_output_dir / "string" / "4002_problem-4002.py").exists()
        assert (temp_output_dir / "string" / "4003_problem-4003.py").exists()

    def test_second_run_is_idempotent(self, sample_challenge, temp_output_dir, temp_catalog):
        day_21 = make_challenge(sample_challenge, "2026-10-21", "4002", "problem-4002")
        source = FakeSource([make_record(day_21)])
        logger = FakeLogger()

        first = run_backfill(
            logger=logger,
            since=date(2026, 10, 21),
            until=date(2026, 10, 21),
            source=source,
        )
        second = run_backfill(
            logger=logger,
            since=date(2026, 10, 21),
            until=date(2026, 10, 21),
            source=source,
        )

        assert first.collected == [date(2026, 10, 21)]
        assert second.missing == []
        assert second.collected == []
        assert read_problem_ids() == ["4002"]
        assert read_occurrences() == [("2026-10-21", "4002")]

    def test_repeated_problem_keeps_one_problem_and_two_occurrences(
        self, sample_challenge, temp_output_dir, temp_catalog
    ):
        first_day = make_challenge(sample_challenge, "2026-10-21", "4002", "problem-4002")
        second_day = make_challenge(sample_challenge, "2026-10-22", "4002", "problem-4002")
        source = FakeSource([make_record(first_day), make_record(second_day)])

        result = run_backfill(
            logger=FakeLogger(),
            since=date(2026, 10, 21),
            until=date(2026, 10, 22),
            source=source,
        )

        assert result.exit_code == 0
        assert read_problem_ids() == ["4002"]
        assert read_occurrences() == [
            ("2026-10-21", "4002"),
            ("2026-10-22", "4002"),
        ]
        assert (temp_output_dir / "string" / "4002_problem-4002.py").exists()

    def test_one_failure_does_not_block_the_other_days(
        self, sample_challenge, temp_output_dir, temp_catalog
    ):
        day_21 = make_challenge(sample_challenge, "2026-10-21", "4002", "problem-4002")
        day_22 = make_challenge(sample_challenge, "2026-10-22", "4003", "problem-4003")
        source = FakeSource([make_record(day_21), make_record(day_22)], failures={"2026-10-21"})

        result = run_backfill(
            logger=FakeLogger(),
            since=date(2026, 10, 21),
            until=date(2026, 10, 22),
            source=source,
        )

        assert result.collected == [date(2026, 10, 22)]
        assert [day for day, _ in result.failed] == [date(2026, 10, 21)]
        assert result.exit_code == 2
        assert read_problem_ids() == ["4003"]

    def test_a_date_without_a_source_record_is_reported(
        self, sample_challenge, temp_output_dir, temp_catalog
    ):
        day_20 = make_challenge(sample_challenge, "2026-10-20", "4001", "problem-4001")
        source = FakeSource([make_record(day_20)])

        result = run_backfill(
            logger=FakeLogger(),
            since=date(2026, 10, 21),
            until=date(2026, 10, 21),
            source=source,
        )

        assert result.skipped == [date(2026, 10, 21)]
        assert result.exit_code == 2

    def test_no_gaps_is_a_success(self, sample_challenge, temp_output_dir, temp_catalog):
        day_21 = make_challenge(sample_challenge, "2026-10-21", "4002", "problem-4002")
        logger = FakeLogger()
        run_daily(logger=logger, collector=lambda: day_21)

        result = run_backfill(
            logger=logger,
            since=date(2026, 10, 21),
            until=date(2026, 10, 21),
            source=FakeSource([]),
        )

        assert result.missing == []
        assert result.status == "ok"
        assert result.exit_code == 0

    def test_invalid_date_is_rejected(self):
        with pytest.raises(BackfillError, match="Invalid since"):
            run_backfill(logger=FakeLogger(), since="21/10/2026", until="2026-10-21")
