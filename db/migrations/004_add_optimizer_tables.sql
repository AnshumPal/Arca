-- Migration 004: Add optimizer tables for Phase 5
-- Run against an existing database:
--   psql $DATABASE_URL -f db/migrations/004_add_optimizer_tables.sql

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
