CREATE EXTENSION IF NOT EXISTS "pgcrypto";

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
