CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── Phase 1+2 ────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS traces (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id    TEXT,
    agent_id      TEXT        NOT NULL DEFAULT 'agent-1',
    input         TEXT        NOT NULL,
    output        TEXT,
    prompt_used   TEXT,
    tools_used    JSONB       DEFAULT '[]',
    latency_ms    INTEGER,
    error         TEXT,
    feedback      INTEGER,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS traces_session_idx ON traces(session_id);
CREATE INDEX IF NOT EXISTS traces_created_idx ON traces(created_at DESC);

-- ─── Phase 3: Evaluation tables ───────────────────────────────────────────────

-- Evaluation run: one row per trace that has been evaluated
CREATE TABLE IF NOT EXISTS eval_runs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id        UUID        NOT NULL REFERENCES traces(id) ON DELETE CASCADE,
    agent_id        TEXT        NOT NULL,
    overall_score   FLOAT       NOT NULL,
    evaluated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    eval_version    TEXT        NOT NULL DEFAULT 'v1',
    UNIQUE(trace_id)
);

-- Individual dimension scores: one row per dimension per eval_run
CREATE TABLE IF NOT EXISTS eval_scores (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    eval_run_id     UUID        NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
    trace_id        UUID        NOT NULL,
    dimension       TEXT        NOT NULL,
    score           FLOAT       NOT NULL,
    reasoning       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS eval_runs_trace_idx     ON eval_runs(trace_id);
CREATE INDEX IF NOT EXISTS eval_runs_agent_idx     ON eval_runs(agent_id);
CREATE INDEX IF NOT EXISTS eval_runs_evaluated_idx ON eval_runs(evaluated_at DESC);
CREATE INDEX IF NOT EXISTS eval_scores_run_idx     ON eval_scores(eval_run_id);
CREATE INDEX IF NOT EXISTS eval_scores_dim_idx     ON eval_scores(dimension);
