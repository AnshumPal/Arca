-- Migration 003: Add sandbox tables for Phase 4
-- Run against an existing database:
--   psql $DATABASE_URL -f db/migrations/003_add_sandbox_tables.sql

-- Sandbox agent registry
CREATE TABLE IF NOT EXISTS sandbox_agents (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT        NOT NULL UNIQUE,
    production_agent_id TEXT        NOT NULL,
    status              TEXT        NOT NULL DEFAULT 'active',
    config              JSONB       NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Sandbox traces — completely separate from production traces table
CREATE TABLE IF NOT EXISTS sandbox_traces (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    sandbox_id          UUID        NOT NULL REFERENCES sandbox_agents(id) ON DELETE CASCADE,
    production_agent_id TEXT        NOT NULL,
    session_id          TEXT,
    input               TEXT        NOT NULL,
    output              TEXT,
    prompt_used         TEXT,
    tools_used          JSONB       DEFAULT '[]',
    latency_ms          INTEGER,
    error               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Sandbox eval scores — same structure as eval_scores but for sandbox_traces
CREATE TABLE IF NOT EXISTS sandbox_eval_scores (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    sandbox_id       UUID        NOT NULL REFERENCES sandbox_agents(id) ON DELETE CASCADE,
    sandbox_trace_id UUID        NOT NULL REFERENCES sandbox_traces(id) ON DELETE CASCADE,
    dimension        TEXT        NOT NULL,
    score            FLOAT       NOT NULL,
    reasoning        TEXT,
    overall_score    FLOAT       NOT NULL,
    evaluated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS sandbox_agents_prod_idx    ON sandbox_agents(production_agent_id);
CREATE INDEX IF NOT EXISTS sandbox_agents_status_idx  ON sandbox_agents(status);
CREATE INDEX IF NOT EXISTS sandbox_traces_sandbox_idx ON sandbox_traces(sandbox_id);
CREATE INDEX IF NOT EXISTS sandbox_traces_created_idx ON sandbox_traces(created_at DESC);
CREATE INDEX IF NOT EXISTS sandbox_eval_sandbox_idx   ON sandbox_eval_scores(sandbox_id);
