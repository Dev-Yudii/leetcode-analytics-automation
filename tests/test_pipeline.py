"""Tests for the order of the pipeline steps and for the idempotency."""

import sqlite3

import pytest

from scripts.pipeline import DEGRADED, FAILED, OK, run_daily


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


def read_rows(db_path):
    with sqlite3.connect(str(db_path)) as conn:
        return conn.execute(
            "SELECT id, title, slug, status FROM leetcode_problems"
        ).fetchall()


class TestRunOrder:
    def test_persists_before_generating(self, sample_challenge, temp_output_dir, temp_db_path, temp_catalog):
        result = run_daily(
            logger=FakeLogger(),
            db_path=temp_db_path,
            collector=lambda: sample_challenge,
        )
        assert result.status == OK
        assert [step.name for step in result.steps] == [
            "collect",
            "validate",
            "determine_file_path",
            "persist",
            "process_topics",
            "generate",
        ]
        assert read_rows(temp_db_path) == [
            ("3863", "Minimum Operations to Sort a String", "minimum-operations-to-sort-a-string", "PENDING")
        ]
        assert (temp_output_dir / "string" / "3863_minimum-operations-to-sort-a-string.py").exists()

    def test_registers_the_topics_in_the_catalog(self, sample_challenge, temp_output_dir, temp_db_path, temp_catalog):
        run_daily(logger=FakeLogger(), db_path=temp_db_path, collector=lambda: sample_challenge)
        import json

        catalog = json.loads(temp_catalog.read_text(encoding="utf-8"))
        assert catalog == [{"id": 1, "name": "String"}]

    def test_keeps_the_collection_warnings(self, sample_challenge, temp_output_dir, temp_db_path, temp_catalog):
        sample_challenge["warnings"] = ["Warning: field 'difficulty' was null — continued anyway"]
        result = run_daily(logger=FakeLogger(), db_path=temp_db_path, collector=lambda: sample_challenge)
        assert result.warnings == ["Warning: field 'difficulty' was null — continued anyway"]


class TestIdempotency:
    def test_second_run_does_not_duplicate_the_row(self, sample_challenge, temp_output_dir, temp_db_path, temp_catalog):
        run_daily(logger=FakeLogger(), db_path=temp_db_path, collector=lambda: sample_challenge)
        result = run_daily(logger=FakeLogger(), db_path=temp_db_path, collector=lambda: sample_challenge)
        assert len(read_rows(temp_db_path)) == 1
        assert result.step("persist").detail == "unchanged"

    def test_second_run_does_not_touch_the_file(self, sample_challenge, temp_output_dir, temp_db_path, temp_catalog):
        run_daily(logger=FakeLogger(), db_path=temp_db_path, collector=lambda: sample_challenge)
        target = temp_output_dir / "string" / "3863_minimum-operations-to-sort-a-string.py"
        target.write_text("# my solution\n", encoding="utf-8")
        run_daily(logger=FakeLogger(), db_path=temp_db_path, collector=lambda: sample_challenge)
        assert target.read_text(encoding="utf-8") == "# my solution\n"

    def test_empty_fields_are_filled_on_the_next_run(self, sample_challenge, temp_output_dir, temp_db_path, temp_catalog):
        incomplete = dict(sample_challenge)
        incomplete["title"] = None
        run_daily(logger=FakeLogger(), db_path=temp_db_path, collector=lambda: incomplete)
        result = run_daily(logger=FakeLogger(), db_path=temp_db_path, collector=lambda: sample_challenge)
        assert result.step("persist").detail == "enriched"
        assert read_rows(temp_db_path)[0][1] == "Minimum Operations to Sort a String"

    def test_collected_values_are_never_overwritten(self, sample_challenge, temp_output_dir, temp_db_path, temp_catalog):
        run_daily(logger=FakeLogger(), db_path=temp_db_path, collector=lambda: sample_challenge)
        changed = dict(sample_challenge)
        changed["title"] = "Another title"
        result = run_daily(logger=FakeLogger(), db_path=temp_db_path, collector=lambda: changed)
        assert result.step("persist").detail == "unchanged"
        assert read_rows(temp_db_path)[0][1] == "Minimum Operations to Sort a String"


class TestFailures:
    def test_missing_identity_is_fatal(self, sample_challenge, temp_output_dir, temp_db_path, temp_catalog):
        sample_challenge["id"] = None
        result = run_daily(logger=FakeLogger(), db_path=temp_db_path, collector=lambda: sample_challenge)
        assert result.status == FAILED
        assert result.exit_code == 1
        assert not temp_db_path.exists()

    def test_collection_error_is_fatal(self, temp_output_dir, temp_db_path, temp_catalog):
        from scripts.collection import CollectionError

        def boom():
            raise CollectionError("Failed to fetch challenge: no connection to LeetCode")

        result = run_daily(logger=FakeLogger(), db_path=temp_db_path, collector=boom)
        assert result.status == FAILED
        assert result.exit_code == 1

    def test_database_failure_still_generates_the_file(self, sample_challenge, temp_output_dir, temp_catalog, tmp_path):
        blocked = tmp_path / "not-a-folder"
        blocked.write_text("x", encoding="utf-8")
        result = run_daily(
            logger=FakeLogger(),
            db_path=blocked / "history.db",
            collector=lambda: sample_challenge,
        )
        assert result.status == DEGRADED
        assert result.exit_code == 2
        assert result.step("persist").status == FAILED
        assert (temp_output_dir / "string" / "3863_minimum-operations-to-sort-a-string.py").exists()

    def test_exit_code_of_a_healthy_run(self, sample_challenge, temp_output_dir, temp_db_path, temp_catalog):
        result = run_daily(logger=FakeLogger(), db_path=temp_db_path, collector=lambda: sample_challenge)
        assert result.exit_code == 0
