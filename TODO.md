# TODO

## In progress

- [x] Review current project state with OpenCode
- [x] Create topics.json (populated incrementally on each collection)
- [x] Implement topic management (catalog + integration in `main.py`)
- [x] New generated-file layout (header with extracted-on/link + `Notes:` section)
- [x] README disclaimer + legal positioning
- [x] Pipeline audit + reliability pass (2026-10-21): steps as callable functions, persist before generate, idempotent writes, real error causes, literal parser, run log, exit codes, 76 tests

## Database

- [ ] Create `problems` table (Postgres — once the Python pipeline is stable)
- [ ] Create `topics` table
- [ ] Create `problem_topics` table
- [ ] Create `collection_runs` / `collection_events` (audit: "did not collect" vs "collection failed")
- [ ] Migrate the 18 collected rows from the legacy `leetcode_problems` table
- [ ] Drop the legacy `category` / `date_generated` columns in favour of `file_path` + `challenge_date` (§21, §22)
- [ ] `problems.file_path` (relative path) and `in_progress_at` / `concluded_at` (§8, §10.1)
- [ ] `status` with `CHECK (status IN ('PENDING','IN_PROGRESS','CONCLUDED'))` (§10)
- [ ] Link `topics.json` to the `topics` table (no independent ID generation, §13)
- [ ] Postgres in Docker Compose with a persistent volume + `pg_dump` backup (§26)

## Pipeline

- [x] Refactor execution order (architecture §17 — generate file last, never gate persistence)
- [x] Implement warnings (collection: missing/null/empty become warnings, only ID blocks)
- [x] Fix exception handling (per-stage blocks with specific messages, no new hierarchy)
- [x] Real literal parser for the examples (no blind `replace`, no `exec` in the generated files)
- [x] Run log + exit codes (`0` ok, `1` nothing collected, `2` degraded)
- [ ] `--conclude <id>`: `PENDING → IN_PROGRESS → CONCLUDED` with timestamps (ideas.md, Phase 1)
- [ ] Decide the fate of the legacy database: export to CSV and rebuild on Postgres

## Later

- [ ] Airflow DAG: `collect → validate → persist → process_topics → generate` (§27)
- [ ] Investigate `dailyCodingChallengeList(year:)` — it may allow replaying past Daily Challenges (§20)
- [ ] Scheduled daily run (Task Scheduler or Airflow)
- [ ] Backup
