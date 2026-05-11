-- Enable pgcrypto for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =========================================================
-- Migration tracking
-- =========================================================

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =========================================================
-- ENUMS
-- =========================================================

CREATE TYPE job_status AS ENUM (
    'pending',
    'running',
    'success',
    'failed',
    'dead'
);

-- =========================================================
-- JOBS
-- =========================================================

CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    job_type TEXT NOT NULL,

    payload JSONB NOT NULL,

    status job_status NOT NULL DEFAULT 'pending',

    attempt_count INTEGER NOT NULL DEFAULT 0,

    max_attempts INTEGER NOT NULL DEFAULT 3,

    scheduled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    started_at TIMESTAMPTZ,

    completed_at TIMESTAMPTZ,

    worker_id TEXT,

    error_message TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =========================================================
-- JOB EVENTS
-- =========================================================

CREATE TABLE job_events (
    id BIGSERIAL PRIMARY KEY,

    job_id UUID NOT NULL
        REFERENCES jobs(id)
        ON DELETE CASCADE,

    event_type TEXT NOT NULL,

    old_status job_status,

    new_status job_status,

    worker_id TEXT,

    metadata JSONB,

    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =========================================================
-- INDEXES
-- =========================================================

CREATE INDEX idx_jobs_status_scheduled
    ON jobs(status, scheduled_at);

CREATE INDEX idx_jobs_pending_scheduled
    ON jobs(scheduled_at)
    WHERE status = 'pending';

CREATE INDEX idx_job_events_job_id
    ON job_events(job_id);
