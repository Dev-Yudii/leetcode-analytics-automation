"""Tests for the order of the pipeline steps and for the idempotency.

The database tests need PostgreSQL. They are skipped when it is not
reachable.
"""

import pytest

from scripts.db_utils import execute_query
from scripts.pipeline import DEGRADED, FAILED, OK, run_daily

pytestmark = pytest.mark.usefixtures("postgres_url")


class FakeLogger:
    """Collects the messages instead of writing them to the console."""

    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(("INFO", message))

    def warning(self, message):
        self.messages.append(("WARN", message))

    def error(self, message):
        self.messages.append(("ERROR", message))


def read_problems():
    return execute_query(
        "SELECT id, title, slug, status, challenge_date, file_path FROM problems ORDER BY id"
    )


class TestRunOrder:
    def test_persists_before_generating(self, sample_challenge, temp_output_dir, temp_catalog):
        result = run_daily(logger=FakeLogger(), collector=lambda: sample_challenge)
        assert result.status == OK
        assert [step.name for step in result.steps] == [
            "collect",
            "validate",
            "determine_file_path",
            "persist",
            "record_daily_challenge",
            "process_topics",
            "persist_problem_topics",
            "generate",
        ]
        rows = read_problems()
        assert len(rows) == 1
        assert rows[0]["id"] == "3863"
        assert rows[0]["status"] == "PENDING"
        assert rows[0]["file_path"] == "string/3863_minimum-operations-to-sort-a-string.py"
        assert str(rows[0]["challenge_date"]) == "2026-10-21"
        assert (temp_output_dir / "string" / "3863_minimum-operations-to-sort-a-string.py").exists()

    def test_file_path_is_relative(self, sample_challenge, temp_output_dir, temp_catalog):
        run_daily(logger=FakeLogger(), collector=lambda: sample_challenge)
        stored = read_problems()[0]["file_path"]
        assert ":" not in stored
        assert not stored.startswith("C")

    def test_records_the_daily_challenge_occurrence(self, sample_challenge, temp_output_dir, temp_catalog):
        result = run_daily(logger=FakeLogger(), collector=lambda: sample_challenge)
        assert result.step("record_daily_challenge").detail == "inserted"
        rows = execute_query("SELECT challenge_date, problem_id FROM daily_challenges")
        assert len(rows) == 1
        assert str(rows[0]["challenge_date"]) == "2026-10-21"
        assert rows[0]["problem_id"] == "3863"

    def test_missing_date_is_recorded_as_skipped(self, sample_challenge, temp_output_dir, temp_catalog):
        sample_challenge["date"] = None
        result = run_daily(logger=FakeLogger(), collector=lambda: sample_challenge)
        assert result.step("record_daily_challenge").detail == "skipped"
        rows = execute_query("SELECT challenge_date FROM daily_challenges")
        assert rows == []

    def test_registers_the_topics_in_the_catalog(self, sample_challenge, temp_output_dir, temp_catalog):
        run_daily(logger=FakeLogger(), collector=lambda: sample_challenge)
        import json

        catalog = json.loads(temp_catalog.read_text(encoding="utf-8"))
        assert catalog == [{"id": 1, "name": "String"}]

    def test_stores_every_topic_of_the_problem(self, sample_challenge, temp_output_dir, temp_catalog):
        sample_challenge["topics"] = ["String", "Hash Table", "Math"]
        run_daily(logger=FakeLogger(), collector=lambda: sample_challenge)
        topics = execute_query(
            "SELECT t.name FROM topics t"
            " JOIN problem_topics pt ON pt.topic_id = t.id"
            " WHERE pt.problem_id = %s ORDER BY t.name",
            ("3863",),
        )
        assert [row["name"] for row in topics] == ["Hash Table", "Math", "String"]

    def test_keeps_the_collection_warnings(self, sample_challenge, temp_output_dir, temp_catalog):
        sample_challenge["warnings"] = ["Warning: field 'difficulty' was null — continued anyway"]
        result = run_daily(logger=FakeLogger(), collector=lambda: sample_challenge)
        assert result.warnings == ["Warning: field 'difficulty' was null — continued anyway"]


class TestAudit:
    def test_records_the_run(self, sample_challenge, temp_output_dir, temp_catalog):
        run_daily(logger=FakeLogger(), collector=lambda: sample_challenge)
        runs = execute_query(
            "SELECT status, problem_id, challenge_date, exit_code FROM collection_runs"
        )
        assert len(runs) == 1
        assert runs[0]["status"] == "ok"
        assert runs[0]["problem_id"] == "3863"
        assert runs[0]["exit_code"] == 0

    def test_records_the_warnings_as_events(self, sample_challenge, temp_output_dir, temp_catalog):
        sample_challenge["warnings"] = ["Warning: field 'difficulty' was null — continued anyway"]
        run_daily(logger=FakeLogger(), collector=lambda: sample_challenge)
        events = execute_query("SELECT level, step, message FROM collection_events")
        assert len(events) == 1
        assert events[0]["level"] == "WARN"
        assert "difficulty" in events[0]["message"]

    def test_records_a_failed_collection(self, temp_output_dir, temp_catalog):
        from scripts.collection import CollectionError

        def boom():
            raise CollectionError("Failed to fetch challenge: no connection to LeetCode")

        result = run_daily(logger=FakeLogger(), collector=boom)
        assert result.status == FAILED
        runs = execute_query("SELECT status, exit_code FROM collection_runs")
        assert runs[0]["status"] == "failed"
        assert runs[0]["exit_code"] == 1


class TestIdempotency:
    def test_second_run_does_not_duplicate_the_row(self, sample_challenge, temp_output_dir, temp_catalog):
        run_daily(logger=FakeLogger(), collector=lambda: sample_challenge)
        result = run_daily(logger=FakeLogger(), collector=lambda: sample_challenge)
        assert len(read_problems()) == 1
        assert result.step("persist").detail == "unchanged"

    def test_second_run_does_not_touch_the_file(self, sample_challenge, temp_output_dir, temp_catalog):
        run_daily(logger=FakeLogger(), collector=lambda: sample_challenge)
        target = temp_output_dir / "string" / "3863_minimum-operations-to-sort-a-string.py"
        target.write_text("# my solution\n", encoding="utf-8")
        run_daily(logger=FakeLogger(), collector=lambda: sample_challenge)
        assert target.read_text(encoding="utf-8") == "# my solution\n"

    def test_empty_fields_are_filled_on_the_next_run(self, sample_challenge, temp_output_dir, temp_catalog):
        incomplete = dict(sample_challenge)
        incomplete["title"] = None
        run_daily(logger=FakeLogger(), collector=lambda: incomplete)
        result = run_daily(logger=FakeLogger(), collector=lambda: sample_challenge)
        assert result.step("persist").detail == "enriched"
        assert read_problems()[0]["title"] == "Minimum Operations to Sort a String"

    def test_collected_values_are_never_overwritten(self, sample_challenge, temp_output_dir, temp_catalog):
        run_daily(logger=FakeLogger(), collector=lambda: sample_challenge)
        changed = dict(sample_challenge)
        changed["title"] = "Another title"
        result = run_daily(logger=FakeLogger(), collector=lambda: changed)
        assert result.step("persist").detail == "unchanged"
        assert read_problems()[0]["title"] == "Minimum Operations to Sort a String"

    def test_repeated_problem_records_each_daily_occurrence(self, sample_challenge, temp_output_dir, temp_catalog):
        run_daily(logger=FakeLogger(), collector=lambda: sample_challenge)

        repeated = dict(sample_challenge)
        repeated["date"] = "2026-10-22"
        result = run_daily(logger=FakeLogger(), collector=lambda: repeated)

        assert result.step("persist").detail == "unchanged"
        assert result.step("record_daily_challenge").detail == "inserted"
        assert len(read_problems()) == 1

        rows = execute_query(
            "SELECT challenge_date, problem_id FROM daily_challenges ORDER BY challenge_date"
        )
        assert [str(row["challenge_date"]) for row in rows] == ["2026-10-21", "2026-10-22"]
        assert [row["problem_id"] for row in rows] == ["3863", "3863"]


class TestFailures:
    def test_missing_identity_is_fatal(self, sample_challenge, temp_output_dir, temp_catalog):
        sample_challenge["id"] = None
        result = run_daily(logger=FakeLogger(), collector=lambda: sample_challenge)
        assert result.status == FAILED
        assert result.exit_code == 1
        assert read_problems() == []

    def test_collection_error_is_fatal(self, temp_output_dir, temp_catalog):
        from scripts.collection import CollectionError

        def boom():
            raise CollectionError("Failed to fetch challenge: no connection to LeetCode")

        result = run_daily(logger=FakeLogger(), collector=boom)
        assert result.status == FAILED
        assert result.exit_code == 1

    def test_database_failure_still_generates_the_file(self, sample_challenge, temp_output_dir, temp_catalog, monkeypatch):
        monkeypatch.setenv("LEETCODE_DB_URL", "postgresql://leetcode:leetcode_local_dev@localhost:5432/nonexistent_db")
        result = run_daily(logger=FakeLogger(), collector=lambda: sample_challenge)
        assert result.status == DEGRADED
        assert result.exit_code == 2
        assert result.step("persist").status == FAILED
        assert (temp_output_dir / "string" / "3863_minimum-operations-to-sort-a-string.py").exists()

    def test_exit_code_of_a_healthy_run(self, sample_challenge, temp_output_dir, temp_catalog):
        result = run_daily(logger=FakeLogger(), collector=lambda: sample_challenge)
        assert result.exit_code == 0
