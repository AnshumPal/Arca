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

CREATE TABLE IF NOT EXISTS eval_runs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id        UUID        NOT NULL REFERENCES traces(id) ON DELETE CASCADE,
    agent_id        TEXT        NOT NULL,
    overall_score   FLOAT       NOT NULL,
    evaluated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    eval_version    TEXT        NOT NULL DEFAULT 'v1',
    UNIQUE(trace_id)
);

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

-- ─── Phase 4: Sandbox tables ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sandbox_agents (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT        NOT NULL UNIQUE,
    production_agent_id TEXT        NOT NULL,
    status              TEXT        NOT NULL DEFAULT 'active',
    config              JSONB       NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

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

-- ─── Phase 5: Optimizer table ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS optimizer_runs (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    status            TEXT        NOT NULL DEFAULT 'running',
    triggered_by      TEXT        NOT NULL DEFAULT 'schedule',
    agents_analyzed   JSONB       NOT NULL DEFAULT '[]',
    findings          JSONB       NOT NULL DEFAULT '[]',
    proposals         JSONB       NOT NULL DEFAULT '[]',
    sandboxes_created JSONB       NOT NULL DEFAULT '[]',
    error             TEXT,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS optimizer_runs_status_idx  ON optimizer_runs(status);
CREATE INDEX IF NOT EXISTS optimizer_runs_started_idx ON optimizer_runs(started_at DESC);
