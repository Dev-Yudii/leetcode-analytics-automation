"""Sync the notebook, the solutions repository and Neon.

The cloud collects the challenge and commits the template to the solutions
repository. This script is the other half of the loop: it runs on the
notebook (Windows Task Scheduler, at logon) and

  1. pulls the solutions repository, so a new template arrives;
  2. pushes the files that carry the "# Solved" marker;
  3. marks them as solved in Neon, using the file's last modification time;
  4. removes the solved file from the notebook — it stays in the repository;
  5. records when a challenge was collected for the first time;
  6. rebuilds a challenge the ledger knows about but the notebook lost.

The solution is not a second file: the template is replaced by the
resolution, in the same file. The repository keeps both versions in its
history, and the notebook only keeps what is still open.

Usage:
    uv run python scripts/sync.py
    uv run python scripts/sync.py --dry-run
"""

import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.generator import generate_daily_file
from scripts.leetcode_client import get_challenge_for_date, get_daily_challenge
from scripts.paths import get_output_path
from scripts.pending_index import PENDING_FILE, render_pending_index, write_pending_index
from scripts.persistence import (
    PersistenceError,
    ensure_schema,
    get_open_problems,
    get_problem,
    mark_solved,
    set_collected_at,
)
from scripts.pipeline import DEGRADED, EXIT_DEGRADED, EXIT_FATAL, EXIT_OK, FAILED, OK
from scripts.redact import redact
from scripts.runlog import RunLogger
from scripts.solution_file import is_solved, problem_id_from_path


class SyncError(Exception):
    """The sync could not complete a step. The message names the cause."""


@dataclass
class SyncResult:
    """What the sync did, and what it could not do."""

    pulled: list[str] = field(default_factory=list)
    pushed: list[str] = field(default_factory=list)
    solved: list[str] = field(default_factory=list)
    collected: list[str] = field(default_factory=list)
    rebuilt: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    status: str = OK
    exit_code: int = EXIT_OK


# --------------------------------------------------------------------------
# git
# --------------------------------------------------------------------------


def _git(args: list[str], repo: Path, check: bool = True):
    """Run a git command inside the repository."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise SyncError(f"git {' '.join(args)} failed: {redact(detail)}")
    return result


def pull(repo: Path) -> str:
    """Bring the repository up to date, keeping the local edits."""
    result = _git(
        ["pull", "--rebase", "--autostash", "origin", "main"], repo, check=False
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise SyncError(f"could not pull the repository: {redact(detail)}")
    return result.stdout.strip()


def commit_and_push(repo: Path, paths: list[str], message: str) -> bool:
    """Stage the given paths, commit them and push to the remote.

    Returns False when there was nothing to commit.
    """
    if not paths:
        return False
    _git(["add", "--", *paths], repo)
    if not _git(["status", "--porcelain", "--", *paths], repo).stdout.strip():
        return False
    _git(["commit", "-m", message], repo)
    _git(["push", "origin", "HEAD:main"], repo)
    return True


def hide_and_remove(repo: Path, relative_path: str) -> None:
    """Keep the file in the repository but not in the notebook.

    `skip-worktree` tells git to ignore the working tree copy: the file
    stays in the remote repository, the local one disappears, and the
    working tree stays clean.
    """
    _git(["update-index", "--skip-worktree", "--", relative_path], repo, check=False)
    (repo / relative_path).unlink(missing_ok=True)


# --------------------------------------------------------------------------
# files
# --------------------------------------------------------------------------


def solution_files(root: Path) -> list[Path]:
    """Every generated solution file under the output folder."""
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.rglob("*.py")
        if ".git" not in path.parts and "__pycache__" not in path.parts
    )


# --------------------------------------------------------------------------
# steps
# --------------------------------------------------------------------------


def _record_collection(problem_id: str, result: SyncResult, logger, dry_run: bool = False) -> None:
    """Write the first collection time of a challenge that reached the notebook."""
    try:
        row = get_problem(problem_id)
    except PersistenceError as e:
        result.warnings.append(f"could not read #{problem_id}: {e}")
        return

    if row is None:
        result.warnings.append(
            f"#{problem_id} has no row in the ledger — the cloud did not record it yet"
        )
        return

    if row.get("collected_at") is not None:
        return

    if dry_run:
        logger.info(f"[dry-run] would record the collection of #{problem_id}")
        return

    try:
        set_collected_at(problem_id)
    except PersistenceError as e:
        result.warnings.append(f"could not record the collection of #{problem_id}: {e}")
        return

    result.collected.append(problem_id)
    logger.info(f"Collected #{problem_id} — it reached the notebook")


def _mark_solved(problem_id: str, solved_at: datetime, result: SyncResult, logger) -> None:
    """Close the challenge in the ledger, using the file's modification time."""
    try:
        mark_solved(problem_id, solved_at)
    except PersistenceError as e:
        result.warnings.append(f"could not mark #{problem_id} as solved: {e}")
        return

    result.solved.append(problem_id)
    logger.info(f"Solved #{problem_id} at {solved_at:%Y-%m-%d %H:%M} UTC")


def _push_solved_files(repo: Path, root: Path, result: SyncResult, logger, dry_run: bool) -> None:
    """Push every local file that carries the solved marker."""
    for path in solution_files(root):
        relative = path.relative_to(repo).as_posix()
        problem_id = problem_id_from_path(path)

        if not problem_id:
            result.warnings.append(f"{relative} does not carry a problem id — skipped")
            continue

        # The collection time is written on the first sighting, whether the
        # file is still open or already carries the marker: the resolution
        # time must always have a starting point.
        _record_collection(problem_id, result, logger, dry_run)

        if not is_solved(path):
            continue

        solved_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        title = ""
        try:
            row = get_problem(problem_id)
            title = (row or {}).get("title") or ""
        except PersistenceError:
            pass

        message = f"solution: #{problem_id} - {title}".rstrip(" -")
        if dry_run:
            logger.info(f"[dry-run] would push {relative} ({message})")
            result.pushed.append(relative)
            continue

        try:
            commit_and_push(repo, [relative], message)
        except SyncError as e:
            result.warnings.append(f"could not push {relative}: {e}")
            logger.error(f"Could not push {relative}: {e}")
            continue

        _mark_solved(problem_id, solved_at, result, logger)
        hide_and_remove(repo, relative)
        result.pushed.append(relative)
        logger.info(f"Pushed {relative} — the file stays in the repository, not in the notebook")


def _rebuild_missing(repo: Path, root: Path, result: SyncResult, logger, dry_run: bool) -> None:
    """Rebuild a challenge the ledger knows but the notebook does not have.

    The cloud is the one that collects. This is the safety net that
    guarantees the notebook holds every open challenge, even when the
    remote push of a generated file failed.
    """
    try:
        open_problems = get_open_problems()
    except PersistenceError as e:
        result.warnings.append(f"could not read the ledger: {e}")
        return

    for row in open_problems:
        relative = row.get("file_path")
        challenge_date = row.get("challenge_date")
        if not relative or not challenge_date:
            continue
        if (root / relative).exists():
            continue

        try:
            data = get_challenge_for_date(challenge_date)
        except Exception as e:
            result.warnings.append(
                f"could not fetch #{row.get('id')} ({challenge_date}): {e}"
            )
            continue

        if dry_run:
            logger.info(f"[dry-run] would rebuild {relative}")
            result.rebuilt.append(relative)
            continue

        try:
            generate_daily_file(data, file_path=root / relative)
        except OSError as e:
            result.warnings.append(f"could not generate {relative}: {e}")
            continue

        try:
            commit_and_push(
                repo, [relative], f"chore: rebuild daily challenge {challenge_date}"
            )
        except SyncError as e:
            result.warnings.append(f"could not push {relative}: {e}")
            continue

        result.rebuilt.append(relative)
        logger.info(f"Rebuilt {relative} — the ledger knew about it, the notebook did not")


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def _missing_today(result: SyncResult, logger) -> str | None:
    """The challenge that is live on LeetCode but absent from the ledger.

    The cloud is the one that collects. When the challenge of the day is
    not in the ledger, the cloud is late — and the index says so instead
    of showing an empty list as if there was nothing to do.

    A LeetCode outage is not the same thing: the check is skipped and
    nothing is reported.
    """
    try:
        data = get_daily_challenge()
    except Exception as e:
        logger.warning(f"could not check the challenge of today: {e}")
        return None

    problem_id = data.get("id")
    if not problem_id:
        return None

    try:
        row = get_problem(problem_id)
    except PersistenceError:
        return None

    if row is not None:
        return None

    label = f"#{problem_id}"
    title = (data.get("title") or "").strip()
    if title:
        label += f" — {title}"
    return label


def _update_pending_index(repo: Path, result: SyncResult, logger, dry_run: bool) -> None:
    """Regenerate the index of the open challenges and publish it.

    It runs after the solutions are pushed and after the missing files
    are rebuilt, so the index describes the state the notebook is really
    in.
    """
    try:
        rows = get_open_problems()
    except PersistenceError as e:
        result.warnings.append(f"could not read the ledger for the index: {e}")
        return

    missing = _missing_today(result, logger)
    if missing:
        result.warnings.append(
            f"the challenge of today is not collected yet ({missing})"
        )

    content = render_pending_index(rows, root=repo, missing_today=missing)

    if dry_run:
        logger.info(
            f"[dry-run] would update {PENDING_FILE} ({len(rows)} open challenge(s))"
        )
        return

    try:
        changed = write_pending_index(repo, content)
    except OSError as e:
        result.warnings.append(f"could not write {PENDING_FILE}: {e}")
        logger.error(f"Could not write {PENDING_FILE}: {e}")
        return

    if changed:
        logger.info(f"Updated {PENDING_FILE} — {len(rows)} open challenge(s)")
    else:
        logger.info(f"{PENDING_FILE} is up to date ({len(rows)} open challenge(s))")

    # The commit is attempted even when the content did not change: the
    # file may be waiting for a push that failed in an earlier run.
    try:
        commit_and_push(
            repo, [PENDING_FILE], "chore: update the open challenges index"
        )
    except SyncError as e:
        result.warnings.append(f"could not push {PENDING_FILE}: {e}")
        logger.error(f"Could not push {PENDING_FILE}: {e}")


def run_sync(logger=None, repo=None, root=None, dry_run: bool = False) -> SyncResult:
    """Run the whole sync. Never raises: the result says what happened."""
    if logger is None:
        from scripts.runlog import RunLogger

        logger = RunLogger()

    result = SyncResult()
    repo = Path(repo) if repo else get_output_path()
    root = Path(root) if root else repo

    if not (repo / ".git").exists():
        result.status = FAILED
        result.exit_code = EXIT_FATAL
        result.warnings.append(f"{repo} is not a git repository — nothing to sync")
        return result

    # The sync must not depend on the cloud having run first: it applies
    # the schema itself, so a missing column is never the reason a
    # resolution fails to be recorded.
    try:
        ensure_schema()
    except PersistenceError as e:
        result.status = FAILED
        result.exit_code = EXIT_FATAL
        result.warnings.append(f"could not prepare the ledger: {e}")
        logger.error(f"Could not prepare the ledger: {e}")
        return result

    try:
        output = pull(repo)
        summary = output.splitlines()[-1] if output else "already up to date"
        result.pulled.append(summary)
        logger.info(f"Git pull: {summary}")
    except SyncError as e:
        result.warnings.append(str(e))
        logger.warning(f"Git pull failed: {e}")

    _push_solved_files(repo, root, result, logger, dry_run)
    _rebuild_missing(repo, root, result, logger, dry_run)
    _update_pending_index(repo, result, logger, dry_run)

    result.status = DEGRADED if result.warnings else OK
    result.exit_code = EXIT_DEGRADED if result.warnings else EXIT_OK
    return result


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Sync the notebook, the solutions repository and Neon"
    )
    parser.add_argument(
        "--repo",
        help="path to the solutions repository (default: the output folder)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would happen without changing anything",
    )
    args = parser.parse_args(argv)

    logger = RunLogger()
    result = run_sync(logger=logger, repo=args.repo, dry_run=args.dry_run)

    logger.info(
        f"Sync: {len(result.pushed)} pushed, {len(result.collected)} collected,"
        f" {len(result.rebuilt)} rebuilt, {len(result.warnings)} warning(s)"
    )
    for warning in result.warnings:
        logger.warning(warning)
    logger.info(f"Sync status: {result.status}")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
