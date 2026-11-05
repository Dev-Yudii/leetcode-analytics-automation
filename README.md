# Personal LeetCode Automation & Data Pipeline

## Description
Personal data pipeline that fetches the LeetCode Daily Challenge via GraphQL (one request per day, no login), validates the response into metadata + collection warnings, tracks topic identity in a versioned catalog, generates a pre-filled Python template — header, starter code and local tests — so I can solve and push to GitHub without hand-editing anything that changes daily, and records the metadata in PostgreSQL.

The generated file is a local practice workspace: it opens in any Python 3 environment (e.g. VS Code) for solving and local test runs; the full submission, with all test cases, happens on LeetCode. Solved files live in the separate [LeetCode Solutions](https://github.com/Dev-Yudii/leetcode) repository; this repo holds only the automation.

The pipeline also supports recovering missed days. LeetCode exposes a monthly Daily Challenge history, so a scheduled run can detect gaps in the database and backfill them when it comes back online.


## Disclaimer
Personal, educational data-pipeline project. Not affiliated with, endorsed, or sponsored by LeetCode.
- One request per day to the public Daily Challenge; no login, no credentials, no Premium content, no automated submissions.
- The tool downloads the daily tests and opens the file in any Python 3 environment (e.g. VS Code) for local practice; the full submission, with all test cases, must be done on LeetCode.
- Generated files keep metadata + link back to the original problem so readers solve it on LeetCode; full statements are not republished or stored.
- Purpose: daily-practice consistency, problem-solving training, learning ETL by doing, and building my own database of solving history.
- Use at your own risk. If you are LeetCode and object to this project, please contact me at dev.yudii@gmail.com — it will be discontinued as soon as the message is seen.


## About This Project
This project started with a simple daily frustration: I wanted to keep my LeetCode Daily Challenge solutions organized, and track my progress on GitHub without wasting time manually copying templates and code snippets.

As someone studying **Data Analytics and Data Engineering**, I realized that instead of just creating a repository of static files, I could build a local automation tool that doubles as a personal data pipeline. Every day it collects the challenge metadata and grows a history of my own solving behavior. In the future, that dataset will feed a Business Intelligence (BI) dashboard with insights about my learning curve and performance — for now, the pipeline's job is to collect reliably, one day at a time.


## Data Source & Collection Strategy
LeetCode offers no conventional REST API — only a GraphQL endpoint. That shaped the project:
- `activeDailyCodingChallengeQuestion` fetches exactly what is needed for today's challenge: identity, difficulty, topics, statement HTML for test extraction, and the official Python3 starter snippet.
- `dailyCodingChallengeV2(year, month)` lists the challenges of a month, which lets the backfill find missing dates.
- `question(titleSlug)` fetches the full data for a specific problem when replaying a past day.

No login, no credentials, and no extra traffic during a healthy daily run.


## Current Tech Stack
* **Python 3.13**: the core programming language for the automation logic.
* **Requests**: to communicate with LeetCode's GraphQL API.
* **PostgreSQL**: the operational database. Neon is the production database; Docker Compose provides a local development/test instance.
* **psycopg 3**: the PostgreSQL driver.
* **GitHub Actions**: scheduled daily collection, tests and connectivity probe.
* **uv**: dependency and environment management.
* **Pathlib & RE**: dynamic folders and test extraction from HTML.
* **ast**: parsing LeetCode examples into real Python literals instead of rewriting text blindly.


## How It Works
1. **Fetch**: one GraphQL request to LeetCode for today's challenge.
2. **Validate**: the response is checked field by field. Missing `questionFrontendId` blocks the run (no valid identity); any other missing/null/empty field becomes a collection warning and the run continues.
3. **Persist**: the problem is registered in PostgreSQL with status `PENDING`. Re-running never creates a duplicate and never overwrites a value that was already collected.
4. **Record occurrence**: `daily_challenges` records which problem was the Daily Challenge on that date. A problem can be reused on another day, so this ledger is separate from the problem catalog.
5. **Topics**: names are normalized and registered in the versioned `data/topics.json` catalog (stable IDs, never reused). The same IDs are written to `topics`, and the problem is linked to all its topics in `problem_topics`.
6. **Generate**: a ready-to-solve file named `{ID}_{slug}.py` is created under the topic folder, with metadata, starter code and local tests. An existing file is never overwritten.

Every step is isolated: a failure in one of them does not cancel the others, it marks the run as *degraded* instead of losing the day. `collection_runs` and `collection_events` keep the audit — that is what tells "did not collect" from "collection failed".

## The Notebook Loop

The cloud collects; the notebook solves. The two halves meet in the solution repository.

```text
GitHub Actions (01:15 UTC)          Your notebook (first login of the day)
──────────────────────────          ─────────────────────────────────────
collect → generate                  scripts/sync.py
  ↓                                    ↓
commit the template                  git pull     → the new template arrives
  ↓                                    ↓
Neon (the ledger)                   you solve it and add "# Solved"
                                     ↓
                                   git push     → the solution goes up
                                     ↓
                                   Neon         → status = CONCLUDED
```

The solution is **not a second file**: the template is replaced by the resolution, in the same file. The repository keeps both versions in its history, and the notebook only keeps what is still open.

* The **repository** is the cloud: it stores every template and every solution.
* **Neon** is the ledger: it stores the metadata and the timestamps.
* The **notebook** is the desk: it holds the open challenges and nothing else.

Three timestamps are tracked per problem:

| Column | Meaning |
| --- | --- |
| `generated_at` | when the cloud extracted the challenge from LeetCode |
| `collected_at` | when the file reached the notebook for the first time |
| `solved_at` | when the file was marked solved (its last modification time) |

The metric that follows is `solved_at - collected_at`: how long the challenge waited for you. The view `v_resolution` exposes `resolution_hours`, `resolution_days` and `cloud_latency_hours`.


## Data Model
- `problems`: one row per LeetCode problem, with the status and the three timestamps.
- `daily_challenges`: one row per date, pointing to the problem that was the Daily Challenge. This records repeated challenges correctly.
- `topics` / `problem_topics`: topic identity from `data/topics.json` and its associations.
- `collection_runs` / `collection_events`: collection audit and warnings.
- `v_resolution`: a view with the resolution time of every solved challenge.

The full design is in [docs/architecture.md](./docs/architecture.md).


## Running

```bash
# 1. the local database (Docker)
docker compose up -d

# 2. the daily collection
uv run python main.py
```

The run appends to `logs/pipeline.log` and exits with `0` (everything went fine), `1` (nothing was collected) or `2` (collected, but a step failed) — so a scheduler can tell success from failure.

### The notebook sync

```bash
# pull the new challenges, push the ones you solved, update the ledger
uv run python scripts/sync.py

# see what it would do, without changing anything
uv run python scripts/sync.py --dry-run
```

The sync runs against the solution repository (the same folder the files live in) and the database. It is safe to run at any time and as often as you want — it applies the schema itself, so it never depends on the cloud having run first.

To mark a challenge as solved, add a line with `# Solved` at the end of the file. The template tells you where. Nothing else is needed: the next sync pushes the solution, records `solved_at` from the file's last modification time, and removes the file from your notebook — it stays in the repository.

> **Do not delete the file yourself.** The solution and its modification time disappear together, and the sync has nothing left to push. Mark it and leave it there.

#### Finding the challenge of the day

A solved file leaves the working tree, so the open challenges end up scattered across the topic folders. The sync writes the answer to one file: `PENDING.md`, at the root of the solutions repository.

```markdown
| Collected | ID | Title | Difficulty | Topics | Waiting | File |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-06 | 1385 | Find the Distance Value… | Easy | Array, Sorting | 1 day | [array/1385_….py](array/1385_….py) |
```

It is regenerated at the end of every sync and published to the repository, so it is never stale. It also says when the challenge of the day is missing from the ledger — that means the cloud is late, not that there is nothing to do.

#### Running it every day, automatically

`scripts/sync_notebook.cmd` is the entry point of the scheduled task. It carries the project path and the `uv` path, so the Task Scheduler only needs to know one file. The output goes to `logs/sync-task.log` — no console window, and the history of the runs is always there.

Create the task in **Task Scheduler** (`taskschd.msc`) with **Create Task** (not the basic one):

| Tab | Setting |
| --- | --- |
| Triggers | New → *Daily*, start at **06:00** |
| Actions | New → *Start a program* → `…\leetcode-analytics-automation\scripts\sync_notebook.cmd` → *Start in*: `…\leetcode-analytics-automation` |
| Conditions | Uncheck *Start only if the computer is on AC power*; check *Start only if a network connection is available*; *If the task is already running* → **Do not start a new instance** |
| Settings | Check *Run the task as soon as possible after a scheduled start is missed*; check *Allow the task to be run on demand*; *If the task fails, restart every* **1 minute**, *up to* **3 times** |

A daily trigger means **one run per day**, never before 06:00, no matter how many times you log in. If the computer was off at 06:00, the task runs the moment you turn it on. The cloud publishes the challenge at 22:15 BRT, so it is always there before the task wakes up.

A failed run is almost always the network not being up yet: the restart rule covers it.

> **Registering it from a script needs an elevated prompt.** The root of the Task Scheduler refuses a programmatic registration for a standard user (*Access denied*). Either create the task by hand with the table above, or run `scripts\register_sync_task.ps1` from an **Administrator** PowerShell — it sets every field of that table and overwrites the task if it already exists.

### Recovering missed days

```bash
# check the last 60 days and recover gaps (default)
uv run python main.py --backfill

# full historical recovery
uv run python main.py --backfill --since 2026-10-01 --until 2026-10-31
```

Backfill detects dates without a `daily_challenges` row, fetches the monthly history, and runs the normal pipeline for each missing day. It is idempotent and continues when one day fails. With no `--since`, the daily scheduled run checks the last `LEETCODE_BACKFILL_DAYS` days.

> **Temporary rule:** since the data was restarted on 2026-11-05, the backfill ignores anything older than that date. Remove `BACKFILL_FLOOR` from `scripts/backfill.py` on **2026-12-05** to restore the full window.

### Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `LEETCODE_DB_URL` | `postgresql://leetcode:leetcode_local_dev@localhost:5432/leetcode_analytics` | Operational database (Neon in production) |
| `LEETCODE_TEST_DB_URL` | derived from `LEETCODE_DB_URL` | Separate database used by the tests |
| `LEETCODE_ADMIN_DB_URL` | — | Database owner, **not stored in `.env`** — see below |
| `LEETCODE_OUTPUT_DIR` | `<user>/Problem-Solving/LeetCode` | Where the solution files live |
| `LEETCODE_DB_TIMEOUT` | `10` | Seconds to wait for the database |
| `LEETCODE_BACKFILL_DAYS` | `60` | Lookback window when `--since` is omitted |

On the notebook, the connection string lives in a local `.env` file (copy `.env.example`). It is gitignored, and a real environment variable always wins over it — so the GitHub Actions secret is never overridden by an accidental local file.

The operational database and the test database are **different servers on purpose**:

```text
LEETCODE_DB_URL      = Neon            ← the pipeline and the sync
LEETCODE_TEST_DB_URL = Docker          ← the test suite
```

The test database is created on the server named by `LEETCODE_TEST_DB_URL`, through the `postgres` maintenance database. This matters because the Neon free plan does not allow `CREATE DATABASE`: with the split above, `uv run pytest` still runs the whole suite locally. Docker only needs to be up when you are testing (`docker compose up -d`).

### A credential is never printed

The rule of the project: **a credential is never printed, the diagnostic shows the shape.** A connection string that reaches a terminal reaches the transcript, and a credential in the transcript is a credential that has to be rotated.

```bash
uv run python scripts/show_db_config.py          # the shape of every connection
uv run python scripts/show_db_config.py --check  # and who the connection really is
```

```text
LEETCODE_DB_URL
  purpose  : the operational database — the pipeline, the sync and the GitHub secret
  source   : .env file
  shape    : postgresql://leetcode_app:***@ep-flat-union-….neon.tech/neondb?sslmode=require
  password : 43 characters (hidden)
```

Never read `.env` raw to check a configuration — `show_db_config.py` answers the same question without the secret. Every error message that leaves the pipeline goes through `scripts/redact.py`, which removes the passwords it knows about.

### Database roles

The pipeline does not run as the database owner. It uses `leetcode_app`, a role that owns the objects it manages — so it can apply the schema — but has no cluster-level powers:

| | `neondb_owner` | `leetcode_app` |
| --- | --- | --- |
| Superuser | no | no |
| Create databases | yes | **no** |
| Create roles | yes | **no** |
| Owns the schema objects | no (since the provisioning) | yes |

Two connections, two purposes:

```text
LEETCODE_DB_URL        = leetcode_app   ← the pipeline, the sync, the GitHub secret
LEETCODE_ADMIN_DB_URL  = neondb_owner   ← only for provisioning a role, and NOT stored
```

The owner credential is **not in `.env`**. It is a cluster-level credential and the file is read by every single run of the pipeline. When a role has to be provisioned, the owner connection string is pasted into the environment for that one command — it is in the Neon console, under *Dashboard → Connection string → neondb_owner*:

```powershell
$env:LEETCODE_ADMIN_DB_URL="postgresql://neondb_owner:...@host/neondb?sslmode=require"

uv run python scripts/provision_app_role.py            # see what it would do
uv run python scripts/provision_app_role.py --apply    # do it
```

The script writes the **application** connection string straight into `.env`. The generated password is never printed and never leaves the machine.

If the owner password has to be rotated — after an exposure, for instance — the same script does it and hands the new connection string over through the clipboard, never through the console:

```powershell
uv run python scripts/provision_app_role.py --rotate-owner
```

### Database tasks

```bash
uv run python scripts/db_utils.py       # run any SQL query
uv run python scripts/export_legacy.py  # archive the old SQLite database
uv run python scripts/migrate_legacy.py # migrate the old rows into PostgreSQL

# independent backup (a Docker volume is not a backup)
docker exec leetcode-postgres pg_dump -U leetcode -d leetcode_analytics \
  --no-owner --no-privileges > backup.sql
```


## Remote automation (GitHub Actions + Neon)

The daily job is designed to run even when the home computer is off:

```text
GitHub Actions (01:15 UTC)
  ├─ recover gaps from the monthly LeetCode history
  ├─ collect today's challenge
  ├─ persist in Neon
  ├─ commit the generated .py to Dev-Yudii/leetcode
  ├─ commit data/topics.json back to this repo
  └─ upload the log and open an issue on failure
```

The cron is written in UTC, which is what GitHub uses. The Daily Challenge changes at 00:00 UTC, so the 01:15 UTC schedule always collects the new challenge — and a daylight saving change in your country never moves the collection off the challenge.

> The schedule is a low-priority trigger: GitHub may start the run hours after the cron time. That is harmless — the backfill window recovers anything the delay left behind.

Workflows:
- `.github/workflows/ci.yml`: tests against a PostgreSQL service container.
- `.github/workflows/probe.yml`: manual smoke test of LeetCode connectivity from a GitHub runner.
- `.github/workflows/collect.yml`: daily schedule, manual `workflow_dispatch`, backfill, commits and alerting.

Required repository secrets:
- `LEETCODE_DB_URL`: the Neon connection string (include `sslmode=require` if required by the provider).
- `SOLUTIONS_REPO_TOKEN`: fine-grained PAT with **Contents: Read and write** on `Dev-Yudii/leetcode` only.

The workflow uses the built-in `GITHUB_TOKEN` to push `data/topics.json` back to this repo and to open failure issues. The PAT is only for the solutions repository.

Run `probe.yml` manually after the first push: it proves that a GitHub runner can reach LeetCode before the schedule depends on it. If LeetCode blocks the runner IP, the daily job fails visibly and the next successful run recovers the gap.

### Free-tier guardrails
- GitHub Actions: free for public repositories; 2,000 minutes/month on a private repo. Keep the spending limit at $0.
- Neon Free: 100 CU-hours and 1 GB per project/month, with scale-to-zero. A daily job uses a tiny fraction of this.
- Keep artifact retention at 14 days and use only `ubuntu-latest` runners.
- Take periodic `pg_dump` backups; the free plan has a short restore window.
- The monthly history request is only made by the backfill, not by a healthy daily run.
- GitHub disables scheduled workflows after 60 days of repository inactivity; any push re-enables the schedule.


## Roadmap
- [x] Daily fetch + local file generation + metadata logging
- [x] Topic catalog with stable IDs + collection warnings
- [x] PostgreSQL (`problems`, `topics`, `problem_topics`) + collection audit
- [x] Idempotent pipeline (safe to re-run, safe to schedule)
- [x] `daily_challenges` occurrence ledger + backfill/catch-up
- [x] Remote runner workflows (CI, connectivity probe, daily collection)
- [x] Notebook sync: the cloud collects, the notebook solves, the ledger tracks
- [x] Resolution timing (`generated_at`, `collected_at`, `solved_at`)
- [ ] Scheduled `pg_dump` backups
- [ ] A read-only database role for the future dashboard
- [ ] A dashboard over `v_resolution` (filters by date, difficulty and topic)

See [TODO.md](./TODO.md) for the current working plan and [CHANGELOG.md](./CHANGELOG.md) for history.
