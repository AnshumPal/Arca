-- Migration 002: Add evaluation tables for Phase 3
-- Run against an existing database:
--   psql $DATABASE_URL -f db/migrations/002_add_eval_tables.sql

-- Evaluation run: one row per trace that has been evaluated
CREATE TABLE IF NOT EXISTS eval_runs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id        UUID        NOT NULL REFERENCES traces(id) ON DELETE CASCADE,
    agent_id        TEXT        NOT NULL,
    overall_score   FLOAT       NOT NULL,   -- 0.0 to 1.0
    evaluated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    eval_version    TEXT        NOT NULL DEFAULT 'v1',
    UNIQUE(trace_id)   -- one eval per trace, update if re-run
);

-- Individual dimension scores: one row per dimension per eval_run
CREATE TABLE IF NOT EXISTS eval_scores (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    eval_run_id     UUID        NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
    trace_id        UUID        NOT NULL,
    dimension       TEXT        NOT NULL,   -- 'latency' | 'length' | 'feedback' | 'error'
    score           FLOAT       NOT NULL,   -- 0.0 to 1.0
    reasoning       TEXT,                   -- short explanation of the score
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS eval_runs_trace_idx     ON eval_runs(trace_id);
CREATE INDEX IF NOT EXISTS eval_runs_agent_idx     ON eval_runs(agent_id);
CREATE INDEX IF NOT EXISTS eval_runs_evaluated_idx ON eval_runs(evaluated_at DESC);
CREATE INDEX IF NOT EXISTS eval_scores_run_idx     ON eval_scores(eval_run_id);
CREATE INDEX IF NOT EXISTS eval_scores_dim_idx     ON eval_scores(dimension);
