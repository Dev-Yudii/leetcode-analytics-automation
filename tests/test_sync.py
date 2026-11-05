"""Tests for the sync between the notebook, the solutions repository and Neon."""

import subprocess
from datetime import date

import pytest

from scripts.db_utils import execute_query
from scripts.pipeline import run_daily
from scripts.sync import run_sync

pytestmark = pytest.mark.usefixtures("postgres_url")

SOLVED_FILE = "string/3863_minimum-operations-to-sort-a-string.py"


@pytest.fixture(autouse=True)
def no_network(monkeypatch, sample_challenge):
    """The sync must not reach the internet during the tests.

    It checks the challenge of the day to know whether the cloud is
    late. Here that answer is fixed.
    """
    import scripts.sync as sync_module

    monkeypatch.setattr(
        sync_module, "get_daily_challenge", lambda: dict(sample_challenge)
    )


class FakeLogger:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(("INFO", message))

    def warning(self, message):
        self.messages.append(("WARN", message))

    def error(self, message):
        self.messages.append(("ERROR", message))


def _git(repo, args):
    subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )


def make_remote(tmp_path):
    """A bare repository that plays the role of the remote."""
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(remote)],
        capture_output=True,
        check=True,
    )
    return remote


def make_repo(tmp_path, remote):
    """A clone of the remote, with one commit already in it."""
    repo = tmp_path / "solutions"
    subprocess.run(
        ["git", "clone", str(remote), str(repo)],
        capture_output=True,
        check=True,
    )
    _git(repo, ["config", "user.name", "test"])
    _git(repo, ["config", "user.email", "test@example.com"])
    (repo / "README.md").write_text("solutions\n", encoding="utf-8")
    _git(repo, ["add", "README.md"])
    _git(repo, ["commit", "-m", "init"])
    _git(repo, ["push", "origin", "main"])
    return repo


def seed_problem(sample_challenge):
    """Store the problem and generate its template, like the cloud does."""
    result = run_daily(logger=FakeLogger(), collector=lambda: sample_challenge)
    assert result.status == "ok"


def read_problem():
    rows = execute_query(
        "SELECT status, generated_at, collected_at, solved_at FROM problems WHERE id = '3863'"
    )
    return rows[0] if rows else None


class TestSync:
    def test_an_open_file_records_the_collection(
        self, tmp_path, monkeypatch, sample_challenge, temp_catalog
    ):
        remote = make_remote(tmp_path)
        repo = make_repo(tmp_path, remote)
        monkeypatch.setenv("LEETCODE_OUTPUT_DIR", str(repo))
        seed_problem(sample_challenge)

        result = run_sync(logger=FakeLogger(), repo=repo)

        assert result.collected == ["3863"]
        row = read_problem()
        assert row["status"] == "IN_PROGRESS"
        assert row["collected_at"] is not None
        assert row["solved_at"] is None

    def test_a_solved_file_is_pushed_and_leaves_the_notebook(
        self, tmp_path, monkeypatch, sample_challenge, temp_catalog
    ):
        remote = make_remote(tmp_path)
        repo = make_repo(tmp_path, remote)
        monkeypatch.setenv("LEETCODE_OUTPUT_DIR", str(repo))
        seed_problem(sample_challenge)

        # the user solves the challenge and marks the file
        target = repo / SOLVED_FILE
        target.write_text(
            target.read_text(encoding="utf-8") + "# Solved\n", encoding="utf-8"
        )

        result = run_sync(logger=FakeLogger(), repo=repo)

        assert result.pushed == [SOLVED_FILE]
        assert not target.exists()

        row = read_problem()
        assert row["status"] == "CONCLUDED"
        assert row["collected_at"] is not None
        assert row["solved_at"] is not None

        # the solution stays in the repository
        remote_files = subprocess.run(
            ["git", "-C", str(remote), "ls-tree", "-r", "--name-only", "main"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        ).stdout
        assert SOLVED_FILE in remote_files

    def test_the_solution_code_alone_does_not_close_the_challenge(
        self, tmp_path, monkeypatch, sample_challenge, temp_catalog
    ):
        remote = make_remote(tmp_path)
        repo = make_repo(tmp_path, remote)
        monkeypatch.setenv("LEETCODE_OUTPUT_DIR", str(repo))
        seed_problem(sample_challenge)

        target = repo / SOLVED_FILE
        target.write_text(
            target.read_text(encoding="utf-8").replace(
                "        pass", "        return 0"
            ),
            encoding="utf-8",
        )

        result = run_sync(logger=FakeLogger(), repo=repo)

        assert result.pushed == []
        assert target.exists()
        assert read_problem()["status"] == "IN_PROGRESS"

    def test_a_missing_file_is_rebuilt(
        self, tmp_path, monkeypatch, sample_challenge, temp_catalog
    ):
        remote = make_remote(tmp_path)
        repo = make_repo(tmp_path, remote)
        monkeypatch.setenv("LEETCODE_OUTPUT_DIR", str(repo))
        seed_problem(sample_challenge)

        # the notebook loses the template
        (repo / SOLVED_FILE).unlink()

        import scripts.sync as sync_module

        monkeypatch.setattr(
            sync_module, "get_challenge_for_date", lambda day: sample_challenge
        )

        result = run_sync(logger=FakeLogger(), repo=repo)

        assert result.rebuilt == [SOLVED_FILE]
        assert (repo / SOLVED_FILE).exists()

    def test_a_file_without_a_row_is_reported(
        self, tmp_path, monkeypatch, temp_catalog
    ):
        remote = make_remote(tmp_path)
        repo = make_repo(tmp_path, remote)
        monkeypatch.setenv("LEETCODE_OUTPUT_DIR", str(repo))

        target = repo / "string" / "9999_unknown-problem.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Solved\n", encoding="utf-8")

        result = run_sync(logger=FakeLogger(), repo=repo)

        # the solution is pushed even without a ledger row: a database
        # hiccup must never cost a resolution. The gap is reported.
        assert result.pushed == ["string/9999_unknown-problem.py"]
        assert any("9999" in warning for warning in result.warnings)
        assert result.exit_code == 2

    def test_a_folder_that_is_not_a_repository_fails(
        self, tmp_path, monkeypatch
    ):
        plain = tmp_path / "not-a-repo"
        plain.mkdir()

        result = run_sync(logger=FakeLogger(), repo=plain)

        assert result.status == "failed"
        assert result.exit_code == 1


class TestPendingIndex:
    """The index of the open challenges, at the root of the repository."""

    def test_the_index_lists_the_open_challenge(
        self, tmp_path, monkeypatch, sample_challenge, temp_catalog
    ):
        remote = make_remote(tmp_path)
        repo = make_repo(tmp_path, remote)
        monkeypatch.setenv("LEETCODE_OUTPUT_DIR", str(repo))
        seed_problem(sample_challenge)

        run_sync(logger=FakeLogger(), repo=repo)

        index = (repo / "PENDING.md").read_text(encoding="utf-8")
        assert "# Open challenges" in index
        assert "3863" in index
        assert "Minimum Operations to Sort a String" in index
        assert SOLVED_FILE in index

    def test_the_index_is_published(
        self, tmp_path, monkeypatch, sample_challenge, temp_catalog
    ):
        remote = make_remote(tmp_path)
        repo = make_repo(tmp_path, remote)
        monkeypatch.setenv("LEETCODE_OUTPUT_DIR", str(repo))
        seed_problem(sample_challenge)

        run_sync(logger=FakeLogger(), repo=repo)

        remote_files = subprocess.run(
            ["git", "-C", str(remote), "ls-tree", "-r", "--name-only", "main"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        ).stdout
        assert "PENDING.md" in remote_files

    def test_a_solved_challenge_leaves_the_index(
        self, tmp_path, monkeypatch, sample_challenge, temp_catalog
    ):
        remote = make_remote(tmp_path)
        repo = make_repo(tmp_path, remote)
        monkeypatch.setenv("LEETCODE_OUTPUT_DIR", str(repo))
        seed_problem(sample_challenge)

        target = repo / SOLVED_FILE
        target.write_text(
            target.read_text(encoding="utf-8") + "# Solved\n", encoding="utf-8"
        )

        run_sync(logger=FakeLogger(), repo=repo)

        index = (repo / "PENDING.md").read_text(encoding="utf-8")
        assert "Nothing open right now." in index
        assert "3863" not in index

    def test_the_index_is_not_committed_again_when_nothing_changed(
        self, tmp_path, monkeypatch, sample_challenge, temp_catalog
    ):
        remote = make_remote(tmp_path)
        repo = make_repo(tmp_path, remote)
        monkeypatch.setenv("LEETCODE_OUTPUT_DIR", str(repo))
        seed_problem(sample_challenge)

        run_sync(logger=FakeLogger(), repo=repo)
        before = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        ).stdout.strip()

        run_sync(logger=FakeLogger(), repo=repo)
        after = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        ).stdout.strip()

        assert before == after

    def test_the_index_reports_a_challenge_the_cloud_has_not_collected(
        self, tmp_path, monkeypatch, temp_catalog
    ):
        remote = make_remote(tmp_path)
        repo = make_repo(tmp_path, remote)
        monkeypatch.setenv("LEETCODE_OUTPUT_DIR", str(repo))

        import scripts.sync as sync_module

        monkeypatch.setattr(
            sync_module,
            "get_daily_challenge",
            lambda: {"id": "4242", "title": "Tomorrow's problem", "date": "2026-10-21"},
        )

        result = run_sync(logger=FakeLogger(), repo=repo)

        index = (repo / "PENDING.md").read_text(encoding="utf-8")
        assert "not collected yet" in index
        assert "4242" in index
        assert any("4242" in warning for warning in result.warnings)

    def test_a_challenge_without_a_file_is_marked_as_not_collected(
        self, tmp_path, monkeypatch, sample_challenge, temp_catalog
    ):
        remote = make_remote(tmp_path)
        repo = make_repo(tmp_path, remote)
        monkeypatch.setenv("LEETCODE_OUTPUT_DIR", str(repo))
        seed_problem(sample_challenge)

        # the ledger knows the challenge, the notebook does not have it
        (repo / SOLVED_FILE).unlink()

        import scripts.sync as sync_module

        monkeypatch.setattr(
            sync_module, "get_challenge_for_date", lambda day: sample_challenge
        )
        monkeypatch.setattr(
            sync_module,
            "get_daily_challenge",
            lambda: {"id": "9999", "title": "Another problem"},
        )

        run_sync(logger=FakeLogger(), repo=repo)

        index = (repo / "PENDING.md").read_text(encoding="utf-8")
        assert "9999" in index
