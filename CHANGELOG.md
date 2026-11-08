# Changelog for leetcode analytics automation
This file goal is tracking the project evolution. I'll use it to note down new features, things that broke, fixes I applied, and the tools/best practices I'm learning along the way.


## 2026-11-05 (Notebook loop)
### What's New
- **The cloud collects, the notebook solves.** The roles are now explicit: the solution repository is the cloud (it stores every template and every solution), Neon is the ledger (metadata, status, timestamps) and the notebook is the desk (it holds the open challenges and nothing else).
- **`scripts/sync.py` (the notebook sync):** runs on the notebook and does both directions — it pulls the repository (the new template arrives), pushes the files that carry the solved marker, updates the ledger and rebuilds a challenge the ledger knows but the notebook lost. It is safe to run at any time and is meant to be triggered by the Windows Task Scheduler at the first login of the day.
- **The solved marker:** the template ends with the instruction to add a line reading `# Solved`. The detection is a line-anchored pattern that accepts `# Solved`, `#solved` and `# --solved`, in any case, and never matches the instruction itself. The solution is **not** a second file: the template is replaced by the resolution, in the same file, and the git history keeps both versions.
- **Lifecycle timestamps:** `problems` now carries `generated_at` (the cloud extracted the challenge), `collected_at` (the file reached the notebook) and `solved_at` (the file was marked solved). The new view `v_resolution` exposes `resolution_hours`, `resolution_days` and `cloud_latency_hours`. The metric that matters is `solved_at - collected_at`: how long the challenge waited on the notebook.
- **A solved file leaves the notebook but stays in the repository.** The git index marks it with `skip-worktree`, so the local deletion is invisible to git: the working tree stays clean, the next pull does not bring the file back and a regeneration never overwrites a resolution.
- **`.env` on the notebook:** `python-dotenv` loads a local, gitignored file that never overrides a real environment variable — the GitHub Actions secret always wins in CI. `.env.example` documents every variable.
- **Data reset:** `scripts/reset_collected_data.py` removes every collected day except the one kept, so the ledger starts from the new daily challenge. The topic catalog in `data/topics.json` is never touched: the IDs stay stable and the `topics` table is rebuilt from the challenges collected from now on.
- **Docs:** README, TODO and `docs/architecture.md` now describe the notebook loop, the timestamps and the marker. The Airflow plan was dropped — GitHub Actions plus one local script is enough for one daily job — and the architecture keeps the pipeline sequence, but the orchestrator changed.
- **The scheduled task has an entry point:** `scripts/sync_notebook.cmd` carries the project path, the `uv` path and the log file, so the Task Scheduler only needs to know one file. Its output goes to `logs/sync-task.log`: no console window, and the history of the runs is always there.
- **The first solution went through the whole loop.** The #1385 was solved on the notebook, marked with `# Solved`, and the sync pushed it, closed the challenge in Neon and removed the file from the notebook. The ledger tells the whole story: `generated_at` 11:24 UTC (the cloud extracted it), `collected_at` 18:21 UTC (it reached the notebook), `solved_at` 18:26 UTC (the file was marked solved) — a resolution time of 5.7 minutes.
- **`PENDING.md`, the index of the open challenges.** A solved file leaves the working tree, so the open challenges end up scattered across the topic folders and finding today's meant opening files one by one. The sync now writes one index at the root of the solutions repository: every open challenge, when it was collected, how long it has been waiting and where its file is. It also reports when the challenge of the day is missing from the ledger — the cloud is late, and that is worth saying out loud instead of showing an empty list.
- **The pipeline no longer runs as the database owner.** `leetcode_app` owns the objects it manages — so it can apply the schema — but it cannot create databases, roles or extensions. `scripts/provision_app_role.py` creates the role and writes the connection string straight into `.env`: the generated password is never printed and never leaves the machine.
- **The template says what running the file does.** The old `"Script generated! Configure your tests below:"` was wrong: the tests below come from the problem statement, there is nothing to configure. The header now adapts — it says the examples are about to run, and asks for manual tests only when the statement had no example that could be translated.
- **The scheduled task runs once a day.** The trigger is a daily one at 06:00, with "run as soon as possible after a missed start" and "do not start a new instance": one execution per day, never before 06:00, no matter how many times the computer is turned on.
- **A credential is never printed; the diagnostic shows the shape.** The rule is now written down (§21.4) and enforced by the code: `scripts/show_db_config.py` prints the shape of every connection — scheme, host, database, user, length of the password — and where the value comes from; `scripts/redact.py` strips the credentials from every message that leaves the pipeline; the owner connection string left `.env` for good, because the file is read by every single run and the owner is a cluster-level credential. It is pasted into the environment for the one command that needs it, and its source is the Neon console.
- **The rotated owner password goes through the clipboard.** `provision_app_role.py --rotate-owner` hands the new connection string over to the clipboard — never to the console, never to a command line, never to a file. The old password dies in the same operation.
- **`COMPLETED.md`, the index of the completed challenges.** The open challenges have their index; the solved ones now have theirs, at the root of the same repository: every challenge already solved, when it was solved and how long it took. The `Resolution` column carries the metric the project exists for — the time between the file reaching the notebook and the challenge being marked as done.
- **The links of the completed index are absolute.** A solved file leaves the working tree, so the relative path would point to nothing in the local clone. The index links to the repository instead, and names the repository in a column of its own. The URL is read from the git remote, not hardcoded.

### Fixes & Tweaks
- **The schedule was disabled by inactivity.** GitHub turns scheduled workflows off after 60 days without a push. A commit in the branch default brought it back, and the first run confirmed it: the collection fired, with the usual delay of a low-priority trigger.
- **The cron moved to 01:15 UTC (22:15 BRT).** The cron is expressed in UTC, which is what GitHub uses, so a daylight saving change in the country never moves the collection off the challenge (it changes at 00:00 UTC). The offset also avoids the crowded top of the hour.
- **A rejected push used to lose the generated files.** The workflow committed and pushed without rebasing: if the notebook pushed a solution in the meantime, the push was refused, the step failed and the templates were gone — the ledger already had the rows, so the backfill skipped those days and never regenerated them. The checkout now uses the full history and the push rebases first.
- **The solution folder is deterministic.** The folder came from the first topic LeetCode returned, and the source does not guarantee the order: the same problem could land in two folders. It now comes from the alphabetically first topic, so a re-run never duplicates a file.
- **The backfill has a floor.** The data was restarted on 2026-11-05, so the backfill ignores anything older. The floor is a single constant in `scripts/backfill.py` and the window is 30 days. Remove the floor on 2026-12-05.
- **The test fixture no longer hangs.** The test suite waited for minutes when PostgreSQL was unreachable; the connection now has a timeout and the tests are skipped instead.
- **The reset and the sync apply the schema themselves.** Both used to assume the cloud had already prepared the database: the reset on a database that had never seen the new columns deleted rows it could not see, and the sync would have failed to record a resolution because `collected_at` did not exist. They call `ensure_schema()` now, so the structure is never the reason something breaks.
- **The reset recovers the generation time.** A problem collected before the `generated_at` column existed had it empty. The reset now reads the collection run's `started_at` and fills it in before the runs are pruned — the #1385 of the first day got its timestamp back.
- **The test database moved to the test server.** The fixture created the test database on the server of the *operational* connection string, which meant two problems: the Neon free plan forbids `CREATE DATABASE`, so 34 tests were skipped, and the test database would have landed on the production server anyway. It is now created on the server named by `LEETCODE_TEST_DB_URL`, through the `postgres` maintenance database. The pipeline talks to Neon; the tests talk to Docker.
- **Tests:** 222 passing, including the solved marker, the deterministic folder, the backfill floor, the reset of the collected data, the two indexes of the challenges, the redaction of the credentials, the masked diagnostic and the whole notebook sync against a real git repository.
- **A credential was exposed and rotated.** A diagnostic command printed the Neon password in the terminal, so it reached the conversation transcript and the local session database of OpenCode. An audit confirmed it was in no repository, no commit, no log and no command history. The password was then rotated by the provisioning script, which generated the new one at runtime and wrote it to `.env` without printing it — the same operation created the application role. A second audit proved that the current application and owner passwords have zero occurrences in the transcript, and that all seven password candidates found in it are rejected by Neon.
- **The owner credential left the `.env`.** It was the only cluster-level credential in a file that every run of the pipeline reads. The provisioning script now writes only the application credential, and actively drops any owner line it finds in the file.
- **The view of the resolutions carries the topics.** `v_resolution` now aggregates them, the same way the open index does. The view is declared *after* `problem_topics` in `db/schema.sql` on purpose: the file is read from the top to the bottom, and a fresh database has to reach that table before the view can be created.
- **The two indexes point at each other.** The open one says where the solved ones are, and the other way around.
- **The comment of `sync_notebook.cmd` was stale.** It still said the task runs at the first logon of the day; the trigger is daily at 06:00.
- **Registering the scheduled task from a script needs an elevated prompt.** The root of the Task Scheduler refuses a programmatic registration for a standard user (*Access denied*). The COM API, `Register-ScheduledTask` and `schtasks /create` all hit the same wall; the task has to be created from an Administrator PowerShell or by hand in the GUI.
- **The suite asks the test server once.** The fixture that points the tests at the test database is function-scoped, so each of the fifty database tests paid the connection timeout on its own: with the Docker container down, the suite spent ten seconds per test — eight and a half minutes — waiting for an answer that was never coming. The server is now probed once per session and every test after it skips immediately. The host of the test connection is the IP instead of `localhost`, because libpq resolves the name to two addresses and its timeout is per address. With the container down, the suite now finishes in six seconds.


## 2026-11-04 (Occurrence ledger + remote runner)
### What's New
- **`daily_challenges` occurrence ledger:** a problem can be the Daily Challenge more than once, so the date-to-problem mapping now lives in its own table instead of overloading `problems.challenge_date`. The pipeline records it right after persistence, and the problem row stays idempotent.
- **Backfill / catch-up (`scripts/backfill.py`):** reads the monthly history from `dailyCodingChallengeV2(year, month)`, finds dates without an occurrence row, and replays the normal pipeline with `question(titleSlug)`. It is idempotent, continues after a failed day, and reports `collected / failed / skipped`. New CLI: `--backfill`, `--since`, `--until`; the default window is `LEETCODE_BACKFILL_DAYS` (60).
- **GraphQL client hardening:** retry with backoff for 429 and 5xx (`MAX_ATTEMPTS = 3`), browser-like `Origin`/`Referer` headers, and separate queries for the monthly list and the per-slug detail.
- **Remote runner workflows:** `ci.yml` (tests with a PostgreSQL service), `probe.yml` (manual LeetCode connectivity smoke test from a GitHub runner) and `collect.yml` (00:30 UTC schedule, backfill window, commit to the solutions repo, commit `data/topics.json`, upload log, open an issue on failure). The PAT is scoped to the solutions repository only.
- **Pilot verified end-to-end:** a clone of the local database was backfilled against the live API. The 4 gaps (2026-10-04, 10-14, 10-18, 10-23) were recovered, taking the clone from 31 to 35 problems/occurrences and 25 to 30 topics; 4 solution files were generated in a temporary directory.
- **Real backfill applied:** the local production database went from 31 to 35 problems/occurrences and 25 to 30 topics, and the 4 missing templates were created under `C:\Dev\Problem-Solving\LeetCode` without overwriting existing files.
- **Docs:** README now covers the remote setup, secrets, configuration and free-tier guardrails; architecture §6/§17–§21/§25–§27 describe the implemented occurrence ledger and remote execution.
- **Tests:** 104 passing, including client retries, gap detection, idempotent replay, repeated-problem occurrences and partial backfill failure.

### Fixes & Tweaks
- **Schema seed removed from `db/schema.sql`:** the old seed ran on every `ensure_schema()` and pre-empted `record_daily_challenge`, making a real insert look like "unchanged". The bootstrap is now `seed_daily_challenges()`, called once at pipeline start and before gap detection. It remains idempotent.
- **Apostrophe normalization:** `str.title()` turned `"Fermat's"` into `"Fermat'S"`; normalization now fixes the letter after an apostrophe, and the catalog entry was corrected.
- **Backfill isolation during the pilot:** the output directory was redirected to a temporary folder and the database was a clone, so no production file or row was touched. The pilot database and temporary files were removed afterwards.


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