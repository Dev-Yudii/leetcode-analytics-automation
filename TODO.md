# TODO

## In progress

- [x] Review current project state with OpenCode
- [x] Create topics.json (populated incrementally on each collection)
- [x] Implement topic management (catalog + integration in `main.py`)
- [x] New generated-file layout (header with extracted-on/link + `Notes:` section)
- [x] README disclaimer + legal positioning

## Database

- [ ] Create `problems` table (Postgres — once the Python pipeline is stable)
- [ ] Create `topics` table
- [ ] Create `problem_topics` table

## Pipeline

- [ ] Refactor execution order (architecture §17 — generate file last, never gate persistence)
- [x] Implement warnings (collection: missing/null/empty become warnings, only ID blocks)
- [x] Fix exception handling (per-stage blocks with specific messages, no new hierarchy)

## Later

- [ ] Collection audit
- [ ] Backup
- [ ] Airflow
