# Changelog for leetcode analytics automation
This file goal is tracking the project evolution. I'll use it to note down new features, things that broke, fixes I applied, and the tools/best practices I'm learning along the way.


## 2026-10-21 (Pass 2 — PostgreSQL)
### What's New
- **PostgreSQL is now the operational database:** `docker-compose.yml` runs `postgres:16-alpine` with a persistent volume, and `db/schema.sql` creates `problems`, `topics`, `problem_topics`, `collection_runs` and `collection_events` — the model of docs/architecture.md (§6, §15, §16, §19).
- **The full topic relationship is stored:** the problem is linked to *every* topic LeetCode returned, not only the first one. The topic IDs come from the versioned catalog `data/topics.json`; the database never invents an ID of its own (§12, §15) and a disagreement between the catalog and the database is an error, not something to repair silently (§13).
- **The pipeline follows §17 completely:** `collect → validate → determine_file_path → persist → process_topics → persist_problem_topics → generate`.
- **Collection audit (`collection_runs` / `collection_events`):** every run is registered before the collection starts and closed with its status, the problem and the exit code; every warning becomes an event. This is what finally tells "did not collect" from "collection failed" — the 3 missing days of the old data had no way to be explained.
- **The legacy SQLite database was exported and migrated:** `scripts/export_legacy.py` writes a CSV archive of the 18 old rows, and `scripts/migrate_legacy.py` rebuilds them in PostgreSQL — reading the complete topic list from the generated files, because the old table had kept only the first topic in a `category` column. The 18 problems now carry 61 topic associations that the old database had lost.
- **`file_path` is stored as a relative path** (`string/3863_minimum-operations-to-sort-a-string.py`), never a machine-specific absolute path (§8).
- **Connection timeout:** the database connection fails after 10 seconds instead of hanging, so a scheduler is never stuck on a database that is not answering.

### Fixes & Tweaks
- **Off-by-one in the upsert:** the row read from the database included the `id` column while the list of completable columns did not, so the comparison was shifted by one and a missing field was never filled. Caught by the new tests.
- **The `problems` table carries the new columns:** `challenge_date` (instead of the misleading `date_generated`), `in_progress_at`, `concluded_at`, `created_at`, `updated_at` and a `CHECK` constraint on `status` (§10, §10.1).




## 2026-10-21 (Pass 1 — reliability)
### What's New
- **Pipeline as callable steps (`scripts/pipeline.py`):** the daily run is now `collect → validate → determine_file_path → persist → process_topics → generate` (architecture §17), with each step isolated and reusable. `main.py` became a thin entry point that only reports the outcome.
- **Persistence no longer depends on the file (`scripts/persistence.py`):** the problem is stored **before** the file is generated and the file is never the condition to persist a problem. Re-running the pipeline can no longer lose a record — that was the most dangerous bug found in the audit.
- **Idempotent writes:** re-running the same Daily Challenge reports `inserted`, `enriched` or `unchanged` and never creates a duplicate row. Only fields that are still empty are filled in; a value that was already collected is never overwritten (§18, §20). The rule is isolated in one function so it can be revised when §20 is closed.
- **Errors state their real cause (§23):** `sqlite3.IntegrityError`, `OperationalError`, `DatabaseError` and `OSError` are handled separately instead of every failure being reported as "Problem already registered". A failing step no longer cancels the others: the run ends as `degraded` and the day is not lost.
- **Real literal parser (`scripts/translator.py`):** the old blind `replace("true"/"false"/"null")` + comma split is gone. The new parser scans the text, keeps string literals verbatim, converts only standalone tokens outside strings and validates the result with `ast.literal_eval`. `s = "a,b"` no longer becomes `s = "a ; b"` (a SyntaxError) and `"nullable"` is no longer corrupted into `"Noneable"`. A value that cannot be parsed becomes a comment instead of broken code.
- **Cleaner generated files:** the test block now uses real Python literals instead of `exec()` with injected strings, and the expected output is a value instead of a quoted string, so the printed comparison is accurate.
- **Run log and exit codes:** every run appends to `logs/pipeline.log` (timestamp, level, message) and `main.py` returns `0` (ok), `1` (nothing collected) or `2` (collected but a step failed) — a scheduler can finally tell success from failure.
- **Transport separated from interpretation (`scripts/collection.py`):** `leetcode_client.py` only talks to LeetCode; `parse_challenge()` is pure and testable without a network call. The collection rules (missing / null / empty, identity) stayed exactly as they were.
- **Configurable paths (`scripts/db_utils.py`):** the output folder and the database can be set with `LEETCODE_OUTPUT_DIR` and `LEETCODE_DB_PATH`, so the project no longer depends on a fixed `C:\Dev\Projects\<repo>` layout.
- **Test coverage:** 66 new tests for the translator, the collection rules, the generator and the pipeline order (76 in total), all green.

### Fixes & Tweaks
- **Windows console encoding:** printing a non-ASCII title used to raise `UnicodeEncodeError` on the cp1252 console and kill the run. The console is now reconfigured with `errors="replace"`.
- **HTML entities:** `clean_html` now uses `html.unescape`, so `&amp;lt;` no longer decodes twice and `&nbsp;` no longer leaks into the text.
- **Example parsing:** only the `Example N:` blocks are read, so an "Input:" mentioned in the description no longer becomes a fake test case.
- **Committed the collected work:** the 18 generated files (2026-10-01 → 10-21) are now in the solutions repository, and the 14 new topics of `data/topics.json` are versioned here — the catalog is persistent identity and must never be lost (§12.1).


## 2026-10-01
### What's New
- **Collection diagnostics (`leetcode_client.py`, `main.py`):** fetch step now distinguishes missing/null/empty per field with `warnings[]` instead of generic `KeyError`; only a missing `questionFrontendId` blocks the run (identity failure, per architecture §3.1). `main.py` runs in three stages (fetch → topics → generate) with specific messages, and registers topics incrementally into `data/topics.json` without touching persistence.
- **Safer test generation (`generator.py`):** Daily test blocks now embed inputs/outputs via `repr()`, so quotes, backslashes and newlines in examples (e.g. `s = "()"`) produce valid Python instead of a `SyntaxError`. The `Expected:` value got the same treatment.
- **Clearer diagnostics:** `main.py` and `leetcode_client.py` messages are all in English now, split by stage — fetch failures, collection warnings (missing/null/empty fields continue with a warning), topic registration, and file generation.
- **New solution file layout:** header shows extraction timestamp (`datetime.now`), source link with a pointer to the full statement, title, difficulty and tags; the trailing `Approach/Issue/Complexity` block was replaced by a single open `Notes:` section.
- **README disclaimer:** added purpose, scope (local practice in VS Code, full submission on LeetCode), and a takedown commitment following market practice for personal GraphQL-based projects.
### Fixes & Tweaks
- **Windows environment rebuild:** recreated `.venv` with the system Python 3.13 (uv-managed 3.12 had its `_ssl` DLL blocked by Application Control), aligned `.python-version` to `3.13`.



## 2026-05-31
### What's New
- **Better Test Parser (`generator.py`):** Re-engineered how auto-generated test cases are handled. Instead of using fragile string splitting over the `=` sign (which broke when problems had multiple parameter assignments), the script now dynamically translates LeetCode primitives (`true`, `false`, `null`) to Python syntax and wraps parameters inside an isolated `exec()` environment. It unpacks them directly into the solution method using dictionary unpacking (`**inputs`), handling the multi-variable test cases automatically without syntax errors.
- **Database utils (`db_utils.py`):** Added structural copy-and-paste query templates (SELECT, UPDATE, DELETE, ALTER) to easily run database operations without rewriting connection logic.
- **Analytical Schema Expansion:** Executed structural table updates to support upcoming tracking features, expanding the `leetcode_problems` schema with 4 new tracking metrics columns: `start_time` (TEXT), `time_spent_minutes` (INTEGER), `runtime_ms` (INTEGER), and `memory_mb` (REAL).
### Fixes & Tweaks
- **Robust Path Management (`pathlib.Path`):** Fully migrated the script architecture from raw string concatenation (`os.path`) to standard `pathlib.Path` objects across `db_utils.py` and `generator.py`. Centralized the base workspace path via `OUTPUT_BASE_PATH` to guarantee the script works perfectly on both Windows and Linux without path errors.



## 2026-05-27
### What's New
- **Created a generic DB engine (`db_utils.py`):** Instead of opening and closing database connections inside every separate script, I centralized everything into one generic function that I can use on other scripts on my program. Now, any part of the project can run SQL commands just by passing a single raw string.
- **SQL Injection protection:** I learned that separating data from the SQL queries using question marks (`?`) binds the inputs safely. I'm still studying exactly how these database attacks work under the hood, but I already implemented this best practice to keep my database secure.
### Fixes & Tweaks
- **Code template enhancement:** I updated the blueprint template that the script creates for daily coding. Now it includes markdown fields to document submission metrics like runtime (ms), memory used (MB), and the percentage of LeetCode users beaten at the time.
- **Problem ID accuracy fix:** I noticed that LeetCode's API was returning an internal database ID that didn't match the actual question number on the website. I swapped the GraphQL field to `questionFrontendId`, and now the problem numbers are perfect.



## 2026-05-26
### The First Step (Initial Release)
- **Project layout setup:** Created the repository workspace and organized the structure by keeping the main entry point (`main.py`) at the root level and all helper scripts inside a `scripts/` folder.
- **API Data Fetcher (`leetcode_client.py`):** Handled the connection to LeetCode's GraphQL API to pull the daily challenge data. I had to add custom headers mimicking a real browser (User-Agent) to prevent their server from blocking my automated requests.
- **File Generator (`generator.py`):** Wrote the script that cleans raw HTML content from the API, dynamically creates category folders based on topics (e.g., *arrays*), and generates a clean `.py` file complete with boilerplate code and auto-filled example test cases.
- **Initial SQLite database:** Set up a `leetcode_history.db` file using SQLite to keep a local log of every problem generated by the pipeline, setting their initial status as `PENDING` by default.
- **Pipeline Orchestrator (`main.py`):** Built the main entry script to tie all these components together, allowing me to trigger the entire end-to-end flow with a single command.