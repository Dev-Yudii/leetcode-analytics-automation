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
Airflow (future)
    orchestration
    observability
```

Python is responsible for semantic validation and transformation.

PostgreSQL is responsible for persistence and structural integrity.

Filesystem operations are handled by Python.

Airflow will eventually orchestrate the pipeline, but it should not become responsible for deciding the meaning or validity of the data.

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

The planned `problems` table is:

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
└── concluded_at
```

Planned structure:

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
```

Fields other than `id` and `file_path` may be `NULL` when the source does not provide the corresponding information.

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

Solution files are currently organized using the first topic returned by LeetCode.

Example:

```text
LeetCode/
└── string/
    └── 115_distinct-subsequences.py
```

This is a filesystem organization rule only.

The first topic must not be interpreted as:

* the official primary topic;
* the most important topic;
* a semantic classification created by the project.

All topics returned by LeetCode must be preserved independently in the relational model.

The topic ordering returned by the source should not be assumed to represent semantic priority unless this is explicitly verified later.

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
process topics
   ↓
persist problem_topics
   ↓
generate file
```

The current implementation may not follow this order yet and must be refactored toward it.

In particular, file generation must not be the condition that determines whether a problem can be persisted.

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

The exact historical behavior for repeated collections and changing source data remains to be finalized.

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

The project may later introduce a more complete audit model such as:

```text
collection_runs
collection_events
```

but this is not required for the first implementation.

---

# 20. Historical data

The project values historical information for future analysis.

The implementation should avoid unnecessarily overwriting information when doing so would destroy useful historical context.

Future design work must address:

* repeated collection of the same problem;
* source fields that change over time;
* fields that were previously missing and later become available;
* changes in topic assignments;
* replaying old Daily Challenges;
* distinguishing current state from historical observations.

This part of the model is not considered fully closed yet.

---

# 21. Current database migration

The project previously used SQLite.

The target architecture uses PostgreSQL.

The old SQLite implementation should not be treated as the final data model.

The migration should eventually remove assumptions such as:

* the old `category` column;
* `date_generated`;
* storing the entire problem content;
* using the first topic as the database category;
* conflating database insertion errors with duplicate records.

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

---

# 26. Backup and persistence

GitHub provides versioning and remote persistence for repository files.

Docker volumes provide database persistence across container recreation but are not themselves a complete backup strategy.

A future independent PostgreSQL backup should be considered, such as:

```text
pg_dump
```

The database backup strategy is not part of the first implementation.

---

# 27. Airflow

Airflow is planned for a later stage.

The Python pipeline should first become reliable and understandable without Airflow.

A possible future DAG is:

```text
collect_daily
      ↓
validate_data
      ↓
persist_problem
      ↓
process_topics
      ↓
generate_file
```

Airflow's responsibility should primarily be:

* scheduling;
* orchestration;
* retries;
* task state;
* observability.

It should not replace the Python layer's semantic validation or business rules.

---

# 28. Development philosophy

The project should evolve according to real requirements.

Do not introduce technology solely because it is commonly used in Data Engineering.

Examples:

* PostgreSQL is justified by relational storage and future analysis.
* `topics.json` is justified by the need for stable topic identity across rebuilds.
* Airflow is justified when orchestration becomes useful.
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
