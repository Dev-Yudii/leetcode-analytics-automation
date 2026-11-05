# TODO

## In progress

- [x] Review current project state with OpenCode
- [x] Create topics.json (populated incrementally on each collection)
- [x] Implement topic management (catalog + integration in `main.py`)
- [x] New generated-file layout (header with extracted-on/link + `Notes:` section)
- [x] README disclaimer + legal positioning
- [x] Pipeline audit + reliability pass (2026-10-21): steps as callable functions, persist before generate, idempotent writes, real error causes, literal parser, run log, exit codes, 76 tests
- [x] PostgreSQL migration (2026-10-21): new schema, topic relationship, collection audit, legacy export
- [x] Daily occurrence ledger + backfill/catch-up (2026-11-04)
- [x] Remote runner workflows (CI, connectivity probe, daily collection)
- [x] Pilot backfill against a clone database: 4 gaps recovered, 35 problems/occurrences (2026-11-04)
- [x] Update `docs/architecture.md` with the remote-runner and occurrence-ledger decisions
- [x] Deploy the GitHub Actions schedule against Neon (2026-11-04, secrets configured)
- [x] Run the connectivity probe from GitHub before enabling the schedule (2026-11-04, green)
- [x] Notebook sync: the cloud collects, the notebook solves, the ledger tracks (2026-11-05)
- [x] Resolution timing: `generated_at`, `collected_at`, `solved_at` + `v_resolution` view (2026-11-05)

## Dated reminders

- [ ] **2026-12-05** — remove `BACKFILL_FLOOR` from `scripts/backfill.py`. The collected data was reset on 2026-11-05 and the backfill ignores anything older until then. The window is 30 days (`LEETCODE_BACKFILL_DAYS` in `collect.yml`).
- [ ] **2026-12-05** — after the floor is gone, confirm that the schedule collects one challenge per day and that the backfill only fills real gaps.

## Database

- [x] Create `problems` table (Postgres)
- [x] Create `topics` table
- [x] Create `problem_topics` table
- [x] Create `daily_challenges` table (one row per date, repeated problems allowed)
- [x] Create `collection_runs` / `collection_events` (audit: "did not collect" vs "collection failed")
- [x] Migrate the 18 collected rows from the legacy `leetcode_problems` table
- [x] Drop the legacy `category` / `date_generated` columns in favour of `file_path` + `challenge_date` (§21, §22)
- [x] `problems.file_path` (relative path) and `in_progress_at` / `concluded_at` (§8, §10.1)
- [x] `status` with `CHECK (status IN ('PENDING','IN_PROGRESS','CONCLUDED'))` (§10)
- [x] Link `topics.json` to the `topics` table (no independent ID generation, §13)
- [x] Postgres in Docker Compose with a persistent volume (§26)
- [x] `generated_at` / `collected_at` / `solved_at` + the `v_resolution` view (§10.2)
- [x] Reset the collected data to 2026-11-05 (`scripts/reset_collected_data.py`)
- [ ] `pg_dump` backup (scheduled) — the volume and Neon free plan are not a backup
- [ ] Delete the legacy SQLite file once the migration is considered stable
- [ ] A read-only role for the dashboard, separate from the writer role

## Pipeline

- [x] Refactor execution order (architecture §17 — generate file last, never gate persistence)
- [x] Implement warnings (collection: missing/null/empty become warnings, only ID blocks)
- [x] Fix exception handling (per-stage blocks with specific messages, no new hierarchy)
- [x] Real literal parser for the examples (no blind `replace`, no `exec` in the generated files)
- [x] Run log + exit codes (`0` ok, `1` nothing collected, `2` degraded)
- [x] Monthly history lookup + per-date replay (`dailyCodingChallengeV2` + `question(titleSlug)`)
- [x] Backfill CLI (`--backfill`, `--since`, `--until`) and gap detection
- [x] Retry/backoff in the GraphQL client for 429/5xx responses
- [x] Run the real backfill against the local production database and solutions repository (2026-11-04)
- [x] Deterministic solution folder (sorted topic), so a re-run never duplicates a file
- [x] Rebase before pushing the generated solutions (a rejected push used to lose the files)
- [x] The solved marker (`# Solved`) and the notebook sync (`scripts/sync.py`)
- [x] `scripts/sync_notebook.cmd`: the entry point of the scheduled task, with the paths and the log file
- [ ] `--conclude <id>`: the marker already closes a challenge automatically; the command is only useful to close one by hand

## Later

- [ ] Scheduled database backup
- [ ] A dashboard over `v_resolution`: filters by date, difficulty and topic, plus the statistics of the solved exercises
- [ ] Consider per-run retry budget for transient LeetCode failures
- [ ] **Create the Windows Task Scheduler entry** (manual, one time): trigger *At log on* with a 30s delay, action `scripts\sync_notebook.cmd`, no AC-power condition, restart every 1 minute up to 3 times. The README has the full table.
