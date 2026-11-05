"""Tests for the reset of the collected data."""

import copy
from datetime import date

import pytest

from scripts.db_utils import execute_query
from scripts.pipeline import run_daily
from scripts.reset_collected_data import preview, reset

pytestmark = pytest.mark.usefixtures("postgres_url")


class FakeLogger:
    def info(self, message):
        pass

    def warning(self, message):
        pass

    def error(self, message):
        pass


def make_challenge(sample_challenge, day, problem_id, slug):
    data = copy.deepcopy(sample_challenge)
    data["id"] = problem_id
    data["date"] = day
    data["title"] = f"Problem {problem_id}"
    data["slug"] = slug
    data["link"] = f"https://leetcode.com/problems/{slug}/"
    return data


def collect(sample_challenge, day, problem_id, slug):
    data = make_challenge(sample_challenge, day, problem_id, slug)
    result = run_daily(logger=FakeLogger(), collector=lambda: data)
    assert result.status == "ok"


def read_problem_ids():
    return [row["id"] for row in execute_query("SELECT id FROM problems ORDER BY id")]


def read_occurrences():
    return [
        str(row["challenge_date"])
        for row in execute_query(
            "SELECT challenge_date FROM daily_challenges ORDER BY challenge_date"
        )
    ]


def read_generated_at(problem_id):
    rows = execute_query(
        "SELECT generated_at FROM problems WHERE id = %s", (problem_id,)
    )
    return rows[0]["generated_at"] if rows else None


class TestReset:
    def test_keeps_one_day_and_removes_the_rest(
        self, sample_challenge, temp_output_dir, temp_catalog
    ):
        collect(sample_challenge, "2026-11-03", "4001", "problem-4001")
        collect(sample_challenge, "2026-11-04", "4002", "problem-4002")
        collect(sample_challenge, "2026-11-05", "4003", "problem-4003")

        report = reset(date(2026, 11, 5))

        assert report["kept"] == 1
        assert report["problems_to_delete"] == 2
        assert report["occurrences_to_delete"] == 2
        assert read_problem_ids() == ["4003"]
        assert read_occurrences() == ["2026-11-05"]

    def test_the_dry_run_changes_nothing(
        self, sample_challenge, temp_output_dir, temp_catalog
    ):
        collect(sample_challenge, "2026-11-04", "4001", "problem-4001")
        collect(sample_challenge, "2026-11-05", "4002", "problem-4002")

        report = reset(date(2026, 11, 5), dry_run=True)

        assert report["problems_to_delete"] == 1
        assert report["occurrences_to_delete"] == 1
        assert read_problem_ids() == ["4001", "4002"]
        assert read_occurrences() == ["2026-11-04", "2026-11-05"]

    def test_the_preview_counts_what_would_be_removed(
        self, sample_challenge, temp_output_dir, temp_catalog
    ):
        collect(sample_challenge, "2026-11-04", "4001", "problem-4001")
        collect(sample_challenge, "2026-11-05", "4002", "problem-4002")

        report = preview(date(2026, 11, 5))

        assert report["kept"] == 1
        assert report["problems_to_delete"] == 1
        assert report["occurrences_to_delete"] == 1

    def test_the_generation_time_is_recovered_from_the_run(
        self, sample_challenge, temp_output_dir, temp_catalog
    ):
        """A problem collected before the column existed has it empty.

        The collection run knows when the challenge was extracted, so the
        reset fills the gap in before the runs are pruned.
        """
        collect(sample_challenge, "2026-11-05", "4003", "problem-4003")

        # simulate the old table: the row exists, the timestamp does not
        execute_query("UPDATE problems SET generated_at = NULL WHERE id = '4003'")
        assert read_generated_at("4003") is None

        report = reset(date(2026, 11, 5))

        assert report["removed"]["generated_at_backfilled"] == 1
        assert read_generated_at("4003") is not None

    def test_an_existing_generation_time_is_not_overwritten(
        self, sample_challenge, temp_output_dir, temp_catalog
    ):
        collect(sample_challenge, "2026-11-05", "4003", "problem-4003")

        original = read_generated_at("4003")
        assert original is not None

        report = reset(date(2026, 11, 5))

        assert report["removed"]["generated_at_backfilled"] == 0
        assert read_generated_at("4003") == original
