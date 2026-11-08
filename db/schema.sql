-- Schema of the LeetCode analytics pipeline.
-- The decisions behind it live in docs/architecture.md.

-- Topics: the identity comes from the versioned catalog data/topics.json.
-- The database never generates an ID on its own (§12, §15).
CREATE TABLE IF NOT EXISTS topics (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

-- Problems: the canonical identity is LeetCode's questionFrontendId (§3).
CREATE TABLE IF NOT EXISTS problems (
    id             VARCHAR(20) PRIMARY KEY NOT NULL,
    title          TEXT,
    slug           TEXT,
    link           TEXT,
    difficulty     TEXT,
    challenge_date DATE,
    file_path      TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'PENDING',
    in_progress_at TIMESTAMPTZ,
    concluded_at   TIMESTAMPTZ,
    generated_at   TIMESTAMPTZ,
    collected_at   TIMESTAMPTZ,
    solved_at      TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT problems_status_check CHECK (status IN ('PENDING', 'IN_PROGRESS', 'CONCLUDED'))
);

-- CREATE TABLE IF NOT EXISTS does not touch a table that already exists,
-- so the columns added after the first release need their own statement.
ALTER TABLE problems ADD COLUMN IF NOT EXISTS generated_at TIMESTAMPTZ;
ALTER TABLE problems ADD COLUMN IF NOT EXISTS collected_at TIMESTAMPTZ;
ALTER TABLE problems ADD COLUMN IF NOT EXISTS solved_at TIMESTAMPTZ;

-- Which problem was the Daily Challenge on each date. A problem can be
-- reused as a Daily Challenge on another day (§20), so this occurrence
-- ledger is separate from the problem catalog.
CREATE TABLE IF NOT EXISTS daily_challenges (
    challenge_date DATE PRIMARY KEY,
    problem_id     VARCHAR(20) NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Every topic returned by LeetCode is kept, not only the first one (§9, §11).
CREATE TABLE IF NOT EXISTS problem_topics (
    problem_id VARCHAR(20) NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
    topic_id   INTEGER NOT NULL REFERENCES topics(id),
    PRIMARY KEY (problem_id, topic_id)
);

-- How long a challenge waited for the user: the resolution time starts
-- when the file reached the notebook and ends when it was marked solved.
--
-- The view is declared after `problem_topics` on purpose: it joins the
-- topics, and a fresh database has to reach that table before the view
-- can be created. The file is read from the top to the bottom.
CREATE OR REPLACE VIEW v_resolution AS
SELECT
    p.id,
    p.title,
    p.difficulty,
    p.challenge_date,
    p.file_path,
    p.status,
    p.generated_at,
    p.collected_at,
    p.solved_at,
    EXTRACT(EPOCH FROM (p.solved_at - p.collected_at)) / 3600.0 AS resolution_hours,
    EXTRACT(EPOCH FROM (p.solved_at - p.collected_at)) / 86400.0 AS resolution_days,
    EXTRACT(EPOCH FROM (p.collected_at - p.generated_at)) / 3600.0 AS cloud_latency_hours,
    COALESCE(string_agg(t.name, ', ' ORDER BY t.name), '') AS topics
FROM problems p
LEFT JOIN problem_topics pt ON pt.problem_id = p.id
LEFT JOIN topics t ON t.id = pt.topic_id
WHERE p.solved_at IS NOT NULL AND p.collected_at IS NOT NULL
GROUP BY p.id;

-- One row per collection run: tells "not collected" from "collection failed" (§19).
CREATE TABLE IF NOT EXISTS collection_runs (
    id             BIGSERIAL PRIMARY KEY,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ,
    status         TEXT NOT NULL,
    problem_id     VARCHAR(20),
    challenge_date DATE,
    exit_code      INTEGER,
    message        TEXT
);

-- The warnings and errors observed during a run (§19).
CREATE TABLE IF NOT EXISTS collection_events (
    id         BIGSERIAL PRIMARY KEY,
    run_id     BIGINT NOT NULL REFERENCES collection_runs(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    level      TEXT NOT NULL,
    step       TEXT,
    message    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS problems_challenge_date_idx ON problems (challenge_date);
CREATE INDEX IF NOT EXISTS daily_challenges_problem_id_idx ON daily_challenges (problem_id);
CREATE INDEX IF NOT EXISTS collection_events_run_idx ON collection_events (run_id);
