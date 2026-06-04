-- Migration 005: Promotion gate + rollback for Phase 6
-- Run against an existing database:
--   psql $DATABASE_URL -f db/migrations/005_add_promotion_tables.sql

-- Every version of every production agent's system prompt
CREATE TABLE IF NOT EXISTS agent_versions (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id      TEXT        NOT NULL,
    version       INTEGER     NOT NULL,
    system_prompt TEXT        NOT NULL,
    promoted_from UUID,
    is_current    BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(agent_id, version)
);

-- One row per promotion attempt
CREATE TABLE IF NOT EXISTS promotions (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    sandbox_id       UUID        NOT NULL REFERENCES sandbox_agents(id),
    agent_id         TEXT        NOT NULL,
    status           TEXT        NOT NULL DEFAULT 'pending',
    gate_passed      BOOLEAN,
    gate_results     JSONB       NOT NULL DEFAULT '{}',
    requested_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at       TIMESTAMPTZ,
    decided_by       TEXT,
    rejection_reason TEXT,
    version_created  INTEGER
);

-- One row per rollback event
CREATE TABLE IF NOT EXISTS rollbacks (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id       TEXT        NOT NULL,
    from_version   INTEGER     NOT NULL,
    to_version     INTEGER     NOT NULL,
    reason         TEXT,
    rolled_back_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS agent_versions_agent_idx   ON agent_versions(agent_id);
CREATE INDEX IF NOT EXISTS agent_versions_current_idx ON agent_versions(agent_id, is_current);
CREATE INDEX IF NOT EXISTS promotions_sandbox_idx     ON promotions(sandbox_id);
CREATE INDEX IF NOT EXISTS promotions_agent_idx       ON promotions(agent_id);
CREATE INDEX IF NOT EXISTS promotions_status_idx      ON promotions(status);
CREATE INDEX IF NOT EXISTS rollbacks_agent_idx        ON rollbacks(agent_id);
