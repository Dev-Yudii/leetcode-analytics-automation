# LeetCode Analytics Automation — Architecture

## 1. Purpose

This project is a personal data and automation layer built around LeetCode.

LeetCode remains the source of truth for the original coding problems and their information. This project does not replace LeetCode and does not determine whether a solution is correct.

The project is responsible for:

* collecting Daily Challenge information;
* validating and transforming collected data;
* persisting relevant data in PostgreSQL;
* maintaining a personal history of collected problems;
* generating and organizing personal solution files;
* supporting future analysis of the accumulated data.

The project is also intended as a practical learning project for Python, SQL, PostgreSQL, ETL, automation, data modeling and, later, orchestration.

---

# 2. Architectural principles

## 2.1 Source of truth

LeetCode is the source of truth for the original problem data.

The local system may transform or organize this information, but it must not invent source data.

When source information is unavailable, the system should preserve the absence rather than fabricate a value.

---

## 2.2 Partial failure is not total failure

A problem in one part of the collected data should not automatically invalidate all other valid information.

For example:

* missing `title` does not necessarily prevent storing a problem;
* missing `topics` does not necessarily prevent storing a problem;
* missing `questionFrontendId` does prevent creating a normal `problems` record because there is no valid problem identity.

Collection anomalies should be preserved as warnings when possible.

---

## 2.3 Separation of responsibilities

The intended architecture is:

```text
LeetCode
    ↓
Python
    collection
    validation
    transformation
    ↓
PostgreSQL
    persistence
    relational integrity
    ↓
Filesystem / Git
    personal solution files
    ↓
GitHub Actions (schedule) + sync.py (notebook)
    orchestration
    observability
```

Python is responsible for semantic validation and transformation.

PostgreSQL is responsible for persistence and structural integrity.

Filesystem operations are handled by Python.

GitHub Actions and the local sync orchestrate the pipeline, but they do not become responsible for deciding the meaning or validity of the data.

---

# 3. Problem identity

The canonical problem identifier is LeetCode's:

```text
questionFrontendId
```

It is stored as:

```sql
id VARCHAR(20) PRIMARY KEY NOT NULL
```

The system must not replace this with:

* LeetCode's internal `questionId`;
* a UUID;
* an arbitrary locally generated identifier.

The project uses the identifier that users see on LeetCode.

---

## 3.1 Missing problem ID

If `questionFrontendId` is unavailable:

* do not create a record in `problems`;
* do not invent an identifier;
* preserve the collection anomaly in a warning/quarantine structure when possible;
* preserve enough information to investigate the original collection.

The absence of the problem ID is a failure of identity, not merely a nullable field.

---

# 4. Source data

The current source is the LeetCode GraphQL endpoint.

The Daily Challenge query currently requests information including:

* `questionFrontendId`
* `date`
* `link`
* `title`
* `titleSlug`
* `difficulty`
* `content`
* `topicTags`
* `codeSnippets`

The Python collection layer transforms the response into an internal representation.

Current mappings:

```text
id            ← questionFrontendId
challenge_date← activeDailyCodingChallengeQuestion.date
title         ← question.title
slug          ← question.titleSlug
link          ← Daily Challenge link transformed into a full URL
difficulty    ← question.difficulty
content       ← question.content
topics        ← topicTags[].name
code_snippet  ← Python3 code snippet
```

Some values are direct source values and some are derived values.

The distinction should be preserved in the implementation.

---

# 5. Missing, null and empty values

The collection layer must distinguish between:

* a field that is absent from the response;
* a field explicitly returned as `null`;
* a field explicitly returned as an empty list `[]`;
* a field explicitly returned as an empty string `""`.

These states are not necessarily equivalent.

Examples:

```text
topics missing
topics = null
topics = []
topics = [ ... ]
```

represent different observations about the source response.

Relevant anomalies should generate warnings for later investigation.

The system should not automatically interpret an empty list as a universal statement about the LeetCode problem. It only means that the API response returned an empty list at collection time.

---

# 6. PostgreSQL — problems

The implemented `problems` table is:

```text
problems
├── id
├── title
├── slug
├── link
├── difficulty
├── challenge_date
├── file_path
├── status
├── in_progress_at
├── concluded_at
├── created_at
└── updated_at
```

Implemented structure (`db/schema.sql`):

```sql
id               VARCHAR(20) PRIMARY KEY NOT NULL
title            TEXT NULL
slug             TEXT NULL
link             TEXT NULL
difficulty       TEXT NULL
challenge_date   DATE NULL
file_path        TEXT NOT NULL
status           TEXT NOT NULL DEFAULT 'PENDING'
in_progress_at   TIMESTAMPTZ NULL
concluded_at     TIMESTAMPTZ NULL
created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
```

Fields other than `id` and `file_path` may be `NULL` when the source does not provide the corresponding information.

The occurrence ledger is a separate table:

```sql
daily_challenges
├── challenge_date DATE PRIMARY KEY
├── problem_id     VARCHAR(20) REFERENCES problems(id) ON DELETE CASCADE
└── created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
```

`problems.challenge_date` is the date observed in the row's original collection. `daily_challenges` is the authoritative date-to-problem mapping and supports the same problem being reused on another date.

---

# 7. Problem content

The full LeetCode `content` field is not stored in PostgreSQL.

The content is usually HTML and may contain:

* formatted text;
* tables;
* images;
* examples;
* other presentation-oriented information.

It is useful during file generation but is not considered valuable analytical data for the operational database.

The generated solution file may contain relevant extracted information from the content.

The original problem can always be revisited through the stored `link`.

Therefore:

```text
content
    ↓
used during generation
    ↓
not persisted in problems
```

---

# 8. File path

Each problem has a relative `file_path`.

Example:

```text
string/115_distinct-subsequences.py
```

The path must not contain a machine-specific absolute path.

`file_path` is `NOT NULL`.

The path represents the expected location of the personal solution file.

It does not, by itself, guarantee that the file physically exists.

The path may later be used by the solution repository or other automation to:

* locate a solution;
* troubleshoot missing files;
* navigate between database records and files;
* access the corresponding personal resolution.

The path must therefore be determined before the problem is persisted.

---

# 9. Filesystem organization

Solution files are organized by topic, using the alphabetically first topic returned by LeetCode.

Example:

```text
LeetCode/
└── string/
    └── 115_distinct-subsequences.py
```

This is a filesystem organization rule only.

The topic that decides the folder must not be interpreted as:

* the official primary topic;
* the most important topic;
* a semantic classification created by the project.

All topics returned by LeetCode must be preserved independently in the relational model.

The topic ordering returned by the source is not assumed to represent semantic priority. The folder is chosen from the sorted topic list, so the path of a problem never depends on the order the source happened to use, and a re-run never creates a second file for the same problem.

---

# 10. Problem status

The status field represents the user's personal progress in solving the problem.

Allowed states:

```text
PENDING
IN_PROGRESS
CONCLUDED
```

The only valid progression is:

```text
PENDING → IN_PROGRESS → CONCLUDED
```

A problem must not transition backwards.

The database should use `TEXT` with a `CHECK` constraint rather than PostgreSQL `ENUM`.

Example:

```sql
CHECK (
    status IN (
        'PENDING',
        'IN_PROGRESS',
        'CONCLUDED'
    )
)
```

The transition is driven by the notebook sync, not by a manual command:

* `PENDING` → `IN_PROGRESS` when the file reaches the notebook;
* `IN_PROGRESS` → `CONCLUDED` when the file carries the solved marker.

---

## 10.1 Status timestamps

`in_progress_at`:

* records when the problem first enters `IN_PROGRESS`;
* is initially `NULL`.

`concluded_at`:

* records when the problem enters `CONCLUDED`;
* is initially `NULL`.

There is no `pending_at`.

Status is a user workflow state.

It does not represent:

* ingestion status;
* pipeline status;
* database synchronization status;
* file generation status.

---

## 10.2 Lifecycle timestamps

Three timestamps describe the journey of a challenge from the source to the notebook:

`generated_at`:

* when the cloud extracted the challenge from LeetCode and generated the template;
* written when the problem is first persisted, and never overwritten.

`collected_at`:

* when the template reached the user's notebook for the first time;
* written by the sync on the first sighting of the file, and never overwritten.

`solved_at`:

* when the user marked the file as solved;
* taken from the file's last modification time, not from the moment the sync ran: the sync may happen hours after the resolution.

The resolution time is the interval between the collection and the resolution:

```text
resolution = solved_at - collected_at
```

It is exposed by the view `v_resolution`, together with `resolution_hours`, `resolution_days` and `cloud_latency_hours` (the time between the generation and the collection).

A challenge that waits several days on the notebook is a challenge the user did not reach. The metric measures consistency, not difficulty.

---

# 11. Topics

Topics are modeled as a many-to-many relationship.

```text
problems N ───────── N topics
```

The model consists of:

```text
topics
├── id
└── name

problem_topics
├── problem_id
└── topic_id
```

A problem can have multiple topics.

A topic can belong to multiple problems.

The complete list of topics returned by LeetCode should be preserved.

---

# 12. Topic identity

Topic IDs must remain stable across installations and machine rebuilds.

A PostgreSQL-generated identity is therefore not sufficient by itself.

The project uses a versioned catalog:

```text
data/
└── topics.json
```

Example:

```json
[
    {
        "id": 1,
        "name": "Array"
    },
    {
        "id": 2,
        "name": "String"
    },
    {
        "id": 3,
        "name": "Dynamic Programming"
    }
]
```

The catalog preserves the relationship:

```text
topic name ↔ persistent topic ID
```

This allows a fresh installation to reconstruct the topic identities without downloading historical solution files.

---

## 12.1 Topic ID rules

The following rules are mandatory:

1. Each topic has one unique ID.
2. Each topic name is unique.
3. Existing topics retain their IDs.
4. New topics receive a new ID.
5. Topic IDs are never reused.
6. A topic that disappears from future LeetCode responses must not have its ID reassigned.
7. The next ID is derived from the highest existing ID in the catalog.
8. `topics.json` is version-controlled with Git.
9. PostgreSQL must use the IDs from the catalog rather than independently generating different IDs.

Example:

```text
Array → 1
String → 2
Hash Table → 3
```

If `String` disappears from future data, ID `2` remains associated with `String`.

A new topic must receive a new ID, not `2`.

---

# 13. topics.json and PostgreSQL

`topics.json` is the persistent catalog of topic identity.

PostgreSQL is the operational relational database.

They have different responsibilities.

```text
topics.json
    ↓
persistent topic identity

PostgreSQL
    ↓
operational topic storage and relationships
```

The system must prevent situations where the same topic has conflicting IDs between the catalog and database.

Example of an invalid state:

```text
topics.json:
String → 2

PostgreSQL:
String → 7
```

The implementation should therefore include consistency checks where appropriate.

---

# 14. Topic normalization

Topic names should be normalized before comparison and persistence.

For example:

```text
"Two pointers"
```

may become:

```text
"Two Pointers"
```

The initial normalization strategy can use Python's `.title()` where appropriate.

However, special cases such as acronyms or terms whose capitalization has semantic meaning may require explicit handling later.

Normalization must be deterministic.

The normalization logic should be centralized rather than duplicated throughout the project.

---

# 15. topics table

The planned table is:

```sql
CREATE TABLE topics (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);
```

The database must not independently generate topic IDs with `IDENTITY`.

The ID is controlled by the persistent catalog.

PostgreSQL remains responsible for enforcing:

* uniqueness of IDs;
* uniqueness of topic names;
* foreign-key integrity.

---

# 16. problem_topics table

The planned association table is:

```sql
CREATE TABLE problem_topics (
    problem_id VARCHAR(20) NOT NULL,
    topic_id INTEGER NOT NULL,

    PRIMARY KEY (problem_id, topic_id),

    FOREIGN KEY (problem_id)
        REFERENCES problems(id)
        ON DELETE CASCADE,

    FOREIGN KEY (topic_id)
        REFERENCES topics(id)
);
```

The composite primary key prevents the same topic from being associated with the same problem more than once.

Deleting a problem removes its associations.

Deleting a problem must not delete the topic itself.

Topics are independent reference data.

---

# 17. Pipeline order

The intended pipeline order is:

```text
collect
   ↓
validate
   ↓
determine file_path
   ↓
persist problem
   ↓
record daily occurrence
   ↓
process topics
   ↓
persist problem_topics
   ↓
generate file
```

This is the implemented order in `scripts/pipeline.py`. File generation must not be the condition that determines whether a problem can be persisted.

The occurrence step is separate from problem persistence because the same problem can be the Daily Challenge more than once. It writes to `daily_challenges`, not to a second `problems` row.

---

# 18. Re-execution

The pipeline must be safe to execute more than once.

Running the same Daily Challenge again must not create duplicate logical records.

Re-execution must also not cause existing topic IDs to change.

The system must distinguish between:

* an already-known problem;
* a newly discovered problem;
* an already-known topic;
* a newly discovered topic;
* a new collection anomaly.

Repeated Daily Challenges are recorded in `daily_challenges` without duplicating the problem. Source fields that change after collection (for example a title correction) remain an open historical-data question; the current rule is to fill empty fields but not overwrite values that were already collected.

---

# 19. Collection warnings

A collection warning is an occurrence observed during data collection.

It is not a property of the LeetCode problem itself.

These concepts must remain separate:

```text
LeetCode problem
        ≠
collection warning
```

One problem may produce multiple warnings across different collection runs.

When possible, a warning should preserve information such as:

* collection date/time;
* Daily Challenge date;
* title;
* slug;
* link;
* reason;
* available source information.

The audit model is implemented as:

```text
collection_runs
collection_events
```

`collection_runs` records the attempt and its outcome; `collection_events` stores the warnings observed during it. This is what allows the system to distinguish "the day was not collected" from "the collection failed" (§21).

---

# 20. Historical data

The project values historical information for future analysis.

The implementation should avoid unnecessarily overwriting information when doing so would destroy useful historical context.

The implemented design covers:

* repeated collection of the same problem — `problems` is idempotent; `daily_challenges` stores each occurrence;
* replaying old Daily Challenges — the monthly history plus `question(titleSlug)` feeds the backfill;
* distinguishing current state from historical observations — `collection_runs` and `collection_events` keep the audit.

Still open:

* source fields that change over time (title corrections, for example);
* fields that were previously missing and later become available;
* changes in topic assignments over time.

This part of the model is not considered fully closed yet.

---

# 21. Current database migration

The project previously used SQLite and now uses PostgreSQL.

The migration removed the old assumptions:

* the old `category` column;
* `date_generated`;
* storing the entire problem content;
* using the first topic as the database category;
* conflating database insertion errors with duplicate records.

The legacy SQLite file was exported to CSV and migrated. It can be deleted once the PostgreSQL setup is considered stable.

## 21.1 The operational database and the test database

The pipeline and the test suite must never share a database.

```text
LEETCODE_DB_URL      → Neon          ← the pipeline and the notebook sync
LEETCODE_TEST_DB_URL → Docker        ← the test suite
```

The reason is technical, not a preference: the test fixture creates and drops the test database, and the Neon free plan does not allow `CREATE DATABASE`. The test database is therefore created on the server named by `LEETCODE_TEST_DB_URL`, through the `postgres` maintenance database, which always exists. The operational connection string is never used to create a database.

The consequence is a clean split: the production database holds exactly the collected data, and a test run never touches it.

## 21.2 The schema is applied by every entry point

A missing column must never be the reason an operation fails. Each entry point that writes to the database applies the schema before it does anything else:

```text
ensure_schema() → apply_schema() → db/schema.sql
```

`db/schema.sql` is idempotent: `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` and `CREATE OR REPLACE VIEW`. The cloud, the notebook sync and the reset script all call it, so none of them depends on the others having run first.

---

# 22. Important distinction: category vs topic

The old system used:

```text
category
```

to represent the first topic used for the solution folder.

This concept should not remain as a database property.

A topic is source data.

A filesystem folder is an organization decision.

Therefore:

```text
topic
    ≠
filesystem category
```

The database should store the complete topic relationship instead of storing a single category.

---

# 23. Error handling

Errors must represent their actual cause.

The application must not catch every database exception and report it as a duplicate record.

For example, these are different situations:

```text
duplicate primary key
connection failure
syntax error
constraint violation
permission error
unexpected application error
```

They must not all be reported as:

```text
Problem already registered.
```

Database exceptions should be handled as specifically as practical.

---

# 24. File generation

The generated `.py` file is a personal resolution record.

It is not intended to be a complete mirror of the LeetCode problem page.

The file should contain useful information such as:

* problem identification;
* title;
* link;
* difficulty;
* topics;
* starter code;
* relevant examples/tests;
* personal notes;
* approach;
* final approach;
* complexity.

The original LeetCode page remains the authoritative source for the complete problem statement.

## 24.1 The solved marker

The template is replaced by the resolution, in the same file: there is no second file for the solution. The repository history keeps both versions, and the diff between them is the record of the work.

The file ends with two things:

```text
Notes:
    - Type your approach, insights and learnings here.
# Add a line reading "# Solved" below when you finish the solution.
```

The user marks the challenge as finished by adding one line:

```text
# Solved
```

The marker is read with a line-anchored pattern that accepts `# Solved`, `#solved` and `# --solved`, in any case, and does not match the instruction line. The detection is based on the content of the file, never on the size of the diff: a file full of solution code and no marker is still an open challenge.

The marker is the only thing that closes a challenge. The sync uses it to decide what to push, when the resolution happened and when the file may leave the notebook.

---

# 25. Repository relationship

The project is intended to work with the separate solution repository.

Conceptually:

```text
LeetCode
    ↓
leetcode-analytics-automation
    ↓
PostgreSQL
    ↓
generated solution files
    ↓
leetcode repository
```

The automation repository is responsible for the collection and data pipeline.

The solution repository stores the user's solution files.

The two repositories should remain loosely coupled.

The automation project should not attempt to replace the solution repository.

## 25.1 Remote execution

The production schedule runs on GitHub Actions, not on the user's machine:

```text
GitHub Actions cron (01:15 UTC)
    ↓
Python pipeline
    ├── Neon PostgreSQL (metadata)
    └── Dev-Yudii/leetcode (generated .py)
```

The workflow has three responsibilities:

* `ci.yml` runs the test suite against a PostgreSQL service container;
* `probe.yml` checks that a GitHub runner can reach LeetCode before the schedule depends on it;
* `collect.yml` runs the backfill window, collects today, commits the generated file, commits `data/topics.json`, uploads the log and opens an issue on failure.

Authentication uses two secrets:

* `LEETCODE_DB_URL` — the Neon connection string;
* `SOLUTIONS_REPO_TOKEN` — a fine-grained PAT scoped to the solutions repository with Contents read/write.

The automation repository itself uses the built-in `GITHUB_TOKEN`.

The catch-up window (`LEETCODE_BACKFILL_DAYS`, default 60 in the code and 30 in the workflow) makes the schedule self-healing: if GitHub delays a run or LeetCode is temporarily unavailable, the next successful run fills the gap.

The schedule is a low-priority trigger and GitHub may start the run hours after the cron time. The delay is harmless: the backfill runs before the collection and covers the days up to yesterday, and the collection always picks the challenge that is active now. The cron is expressed in UTC, so a daylight saving change in the user's country never moves the collection off the challenge.

## 25.2 The notebook loop

The cloud collects; the notebook solves. The two halves meet in the solution repository.

```text
GitHub Actions                    Notebook (scripts/sync.py)
──────────────                    ─────────────────────────
collect → generate                git pull    → the template arrives
commit the template               the user solves it
                                  # Solved
Neon (the ledger)                 git push    → the solution goes up
                                  Neon        → status = CONCLUDED
```

The three roles are clear:

* the **repository** is the cloud — it stores every template and every solution;
* **Neon** is the ledger — it stores the metadata, the status and the timestamps;
* the **notebook** is the desk — it holds the open challenges and nothing else.

The sync is the only component that writes to the repository from the notebook, and it is safe to run at any time: it pulls, pushes what carries the marker, updates the ledger and rebuilds a challenge the ledger knows but the notebook lost.

A solved file leaves the notebook but stays in the repository. The git index marks it with `skip-worktree`, so the local deletion is invisible to git: the working tree stays clean, the next pull does not bring the file back, and the solution is never overwritten by a regeneration.

---

# 26. Backup and persistence

GitHub provides versioning and remote persistence for repository files.

Docker volumes provide database persistence across container recreation but are not themselves a complete backup strategy.

An independent PostgreSQL backup is now more important because production metadata lives in Neon:

```text
pg_dump
```

The manual backup command is documented in the README. A scheduled backup is still pending; the Neon free plan does not replace an owned dump.

Free-tier guardrails:

* GitHub Actions is free for public repositories and has 2,000 minutes/month on private ones; keep the spending limit at $0 and use `ubuntu-latest`.
* Neon Free scales to zero and includes 100 CU-hours and 1 GB per project/month; a daily job uses a small fraction of that.
* Artifact retention is 14 days and the monthly LeetCode history is only requested by the backfill, not by a healthy daily run.

---

# 27. Orchestration

The orchestration is GitHub Actions plus a single local script. Airflow was considered and dropped: the pipeline has one daily step and one local step, and a scheduler that needs its own database, its own deployment and its own operational surface would cost more than it solves.

What the scheduler provides:

* the daily schedule;
* the retries;
* the run log and the artifacts;
* the failure issue.

What the local script provides:

* the pull of the new challenge;
* the push of the resolution;
* the update of the ledger;
* the rebuild of a missing file.

The Python layer keeps the semantic validation and the business rules. Neither the scheduler nor the notebook decides anything about the data.

The Airflow DAG that was once planned here would have been:

```text
detect_missing_dates
      ↓
collect_daily
      ↓
validate_data
      ↓
persist_problem
      ↓
record_daily_challenge
      ↓
process_topics
      ↓
generate_file
```

That sequence still describes the pipeline, and it still runs as callable steps (`scripts/pipeline.py`). Only the orchestrator changed.

---

# 28. Development philosophy

The project should evolve according to real requirements.

Do not introduce technology solely because it is commonly used in Data Engineering.

Examples:

* PostgreSQL is justified by relational storage and future analysis.
* `topics.json` is justified by the need for stable topic identity across rebuilds.
* GitHub Actions is justified because the collection must run while the home machine is off.
* Neon is justified because a scheduled remote runner needs a database that is not on the home network.
* `daily_challenges` is justified because the same problem can be reused as a Daily Challenge.
* The notebook sync is justified because the collection runs in the cloud while the resolution happens on the machine.
* Airflow was considered and dropped: the current cron + catch-up window + one local script is enough for one daily job.
* Additional infrastructure should only be introduced when the project has a concrete need for it.

The goal is a coherent system, not a collection of technologies.

---

# 29. Architectural changes

This document represents decisions already made.

Before changing a decision that affects:

* data identity;
* database relationships;
* source-of-truth assumptions;
* persistence strategy;
* topic identity;
* problem status;
* pipeline responsibilities;

the change should be explicitly discussed and agreed upon.

Implementation details may change without changing the architecture.

When implementation reveals a conflict or missing requirement, stop and surface the issue rather than silently changing the architectural decision.
