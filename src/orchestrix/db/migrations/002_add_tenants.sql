-- =========================================================
-- TENANTS
-- =========================================================

CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    name TEXT NOT NULL UNIQUE,

    rate_limit_rps DOUBLE PRECISION NOT NULL DEFAULT 10,

    burst_capacity INTEGER NOT NULL DEFAULT 20,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =========================================================
-- JOB -> TENANT RELATIONSHIP
-- =========================================================

ALTER TABLE jobs
ADD COLUMN tenant_id UUID NOT NULL
REFERENCES tenants(id)
ON DELETE CASCADE;

-- =========================================================
-- INDEXES
-- =========================================================

CREATE INDEX idx_jobs_tenant_id
    ON jobs(tenant_id);

CREATE INDEX idx_jobs_tenant_status
    ON jobs(tenant_id, status);
