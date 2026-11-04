"""The daily pipeline, written as callable steps.

The order follows docs/architecture.md (section 17):

    collect -> validate -> determine file_path -> persist problem
            -> record daily occurrence -> process topics -> generate file

Two rules shape the code:
    * generating the file is never the condition to persist a problem;
    * a failure in one step does not cancel the others. The run ends
      "degraded" instead of losing the day.
"""

from dataclasses import dataclass, field

from scripts.collection import CollectionError
from scripts.generator import determine_file_path, generate_daily_file, relative_file_path
from scripts.leetcode_client import get_daily_challenge
from scripts.persistence import (
    PersistenceError,
    add_event,
    finish_run,
    link_problem_topics,
    record_daily_challenge,
    seed_daily_challenges,
    start_run,
    sync_topics,
    upsert_problem,
)
from scripts.topics import get_or_create_topic_id, normalize_topic_name

OK = "ok"
DEGRADED = "degraded"
FAILED = "failed"

EXIT_OK = 0
EXIT_FATAL = 1
EXIT_DEGRADED = 2


@dataclass
class StepOutcome:
    """Result of one pipeline step."""

    name: str
    status: str
    detail: str = ""


@dataclass
class RunResult:
    """Result of a whole run."""

    status: str = FAILED
    data: dict | None = None
    file_path: str | None = None
    steps: list[StepOutcome] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        if self.status == OK:
            return EXIT_OK
        if self.status == DEGRADED:
            return EXIT_DEGRADED
        return EXIT_FATAL

    def step(self, name: str) -> StepOutcome | None:
        for outcome in self.steps:
            if outcome.name == name:
                return outcome
        return None


def collect() -> dict:
    """Fetch and interpret the Daily Challenge. One request per day."""
    return get_daily_challenge()


def validate(data: dict) -> list[str]:
    """Check the identity of the problem and return the collection warnings.

    A missing identity is fatal: there is no valid problem to work with
    (docs/architecture.md, section 3.1).
    """
    problem_id = data.get("id")
    if problem_id is None or (isinstance(problem_id, str) and not problem_id.strip()):
        raise CollectionError(
            "Challenge without ID (questionFrontendId missing). Skipping save. "
            f"Seen: title={data.get('title')!r} date={data.get('date')!r}"
        )
    return list(data.get("warnings") or [])


def determine_path(data: dict):
    """Work out where the solution file will live, before persisting."""
    return determine_file_path(data)


def persist(data: dict, file_path: str) -> str:
    """Store the problem. Returns inserted, enriched or unchanged."""
    return upsert_problem(data, file_path=file_path)


def process_topics(data: dict, logger=None) -> dict:
    """Register the topics in the versioned catalog.

    Returns {normalized name: topic id}. A catalog failure never blocks the
    rest of the run.
    """
    topic_ids = {}
    raw_topics = data.get("topics")
    if not isinstance(raw_topics, list):
        if logger:
            logger.warning("field 'topics' in unexpected format — no topic registered")
        return topic_ids

    for raw_name in raw_topics:
        if not isinstance(raw_name, str) or not raw_name.strip():
            if logger:
                logger.warning(f"invalid topic {raw_name!r} — skipped the item")
            continue
        normalized = normalize_topic_name(raw_name)
        try:
            topic_ids[normalized] = get_or_create_topic_id(raw_name)
        except Exception as e:
            if logger:
                logger.warning(f"failed to register topic '{normalized}': {e}. Continued anyway.")
    return topic_ids


def persist_topics(problem_id: str, topic_ids: dict) -> int:
    """Write the topics to the database and link them to the problem."""
    sync_topics(topic_ids)
    return link_problem_topics(problem_id, topic_ids)


def generate(data: dict, file_path=None) -> str:
    """Write the solution file. Never overwrites an existing one."""
    return generate_daily_file(data, file_path=file_path)


def run_daily(logger=None, collector=None) -> RunResult:
    """Run the whole pipeline.

    Never raises: the returned result says what happened on every step.
    """
    if logger is None:
        from scripts.runlog import RunLogger

        logger = RunLogger()

    result = RunResult()

    # Older databases may have problems without an occurrence row. Bootstrap
    # the ledger before anything else, without blocking an offline run.
    try:
        seed_daily_challenges()
    except Exception as e:
        logger.warning(f"could not seed the daily challenge ledger: {e}")

    # The run is registered before anything happens, so a failure is
    # recorded too and "not collected" can be told from "collection failed".
    run_id = None
    try:
        run_id = start_run()
    except PersistenceError as e:
        logger.warning(f"could not open the collection run record: {e}")
    except Exception as e:
        logger.warning(f"could not open the collection run record: {e!r}")

    # 1. collect
    try:
        data = collector() if collector else collect()
    except CollectionError as e:
        logger.error(f"Collection failed: {e}")
        result.steps.append(StepOutcome("collect", FAILED, str(e)))
        result.status = FAILED
        add_event(run_id, "ERROR", "collect", str(e))
        finish_run(run_id, FAILED, exit_code=result.exit_code, message=str(e))
        return result
    except Exception as e:
        logger.error(f"Collection failed with an unexpected error: {e!r}")
        result.steps.append(StepOutcome("collect", FAILED, repr(e)))
        result.status = FAILED
        add_event(run_id, "ERROR", "collect", repr(e))
        finish_run(run_id, FAILED, exit_code=result.exit_code, message=repr(e))
        return result

    result.data = data
    result.steps.append(
        StepOutcome("collect", OK, f"problem {data.get('id')} — {data.get('title')}")
    )

    # 2. validate
    try:
        warnings = validate(data)
    except CollectionError as e:
        logger.error(str(e))
        result.steps.append(StepOutcome("validate", FAILED, str(e)))
        result.status = FAILED
        add_event(run_id, "ERROR", "validate", str(e))
        finish_run(run_id, FAILED, exit_code=result.exit_code, message=str(e))
        return result

    result.warnings = warnings
    for warning in warnings:
        logger.warning(warning)
        add_event(run_id, "WARN", "validate", warning)
    result.steps.append(
        StepOutcome("validate", OK, f"{len(warnings)} collection warning(s)")
    )

    # 3. determine file path
    relative = relative_file_path(data)
    file_path = determine_path(data)
    result.file_path = str(file_path)
    result.steps.append(StepOutcome("determine_file_path", OK, relative))

    # 4. persist the problem
    try:
        outcome = persist(data, file_path=relative)
        logger.info(f"Database: {outcome} ({relative})")
        result.steps.append(StepOutcome("persist", OK, outcome))
    except PersistenceError as e:
        logger.error(f"Database error: {e}")
        result.steps.append(StepOutcome("persist", FAILED, str(e)))
        add_event(run_id, "ERROR", "persist", str(e))
        result.status = DEGRADED
    except Exception as e:
        logger.error(f"Database error (unexpected): {e!r}")
        result.steps.append(StepOutcome("persist", FAILED, repr(e)))
        add_event(run_id, "ERROR", "persist", repr(e))
        result.status = DEGRADED

    # 5. record the daily occurrence (a problem can be reused on another day)
    try:
        occurrence = record_daily_challenge(data.get("date"), data.get("id"))
        logger.info(f"Daily challenge: {occurrence} ({data.get('date')})")
        result.steps.append(StepOutcome("record_daily_challenge", OK, occurrence))
    except PersistenceError as e:
        logger.error(f"Daily challenge record failed: {e}")
        result.steps.append(StepOutcome("record_daily_challenge", FAILED, str(e)))
        add_event(run_id, "ERROR", "record_daily_challenge", str(e))
        result.status = DEGRADED
    except Exception as e:
        logger.error(f"Daily challenge record failed (unexpected): {e!r}")
        result.steps.append(StepOutcome("record_daily_challenge", FAILED, repr(e)))
        add_event(run_id, "ERROR", "record_daily_challenge", repr(e))
        result.status = DEGRADED

    # 6. process topics (versioned catalog)
    topic_ids = {}
    try:
        topic_ids = process_topics(data, logger=logger)
        summary = ", ".join(f"{name}->{topic_id}" for name, topic_id in topic_ids.items())
        logger.info(f"Topics: {summary}" if summary else "Topics: none registered")
        result.steps.append(StepOutcome("process_topics", OK, summary))
    except Exception as e:
        logger.error(f"Topic registration failed: {e!r}")
        result.steps.append(StepOutcome("process_topics", FAILED, repr(e)))
        add_event(run_id, "ERROR", "process_topics", repr(e))
        result.status = DEGRADED

    # 7. persist the topic relationship
    try:
        linked = persist_topics(data.get("id"), topic_ids)
        logger.info(f"Problem topics: {linked} new association(s)")
        result.steps.append(StepOutcome("persist_problem_topics", OK, f"{linked} new association(s)"))
    except PersistenceError as e:
        logger.error(f"Topic association failed: {e}")
        result.steps.append(StepOutcome("persist_problem_topics", FAILED, str(e)))
        add_event(run_id, "ERROR", "persist_problem_topics", str(e))
        result.status = DEGRADED
    except Exception as e:
        logger.error(f"Topic association failed (unexpected): {e!r}")
        result.steps.append(StepOutcome("persist_problem_topics", FAILED, repr(e)))
        add_event(run_id, "ERROR", "persist_problem_topics", repr(e))
        result.status = DEGRADED

    # 8. generate the file
    try:
        path = generate(data, file_path=file_path)
        logger.info(f"File: {path}")
        result.steps.append(StepOutcome("generate", OK, path))
    except OSError as e:
        logger.error(f"File generation failed: {e}")
        result.steps.append(StepOutcome("generate", FAILED, str(e)))
        add_event(run_id, "ERROR", "generate", str(e))
        result.status = DEGRADED
    except Exception as e:
        logger.error(f"File generation failed (unexpected): {e!r}")
        result.steps.append(StepOutcome("generate", FAILED, repr(e)))
        add_event(run_id, "ERROR", "generate", repr(e))
        result.status = DEGRADED

    if result.status != DEGRADED:
        result.status = OK

    finish_run(
        run_id,
        result.status,
        problem_id=data.get("id"),
        challenge_date=data.get("date"),
        exit_code=result.exit_code,
        message=relative,
    )
    return result
