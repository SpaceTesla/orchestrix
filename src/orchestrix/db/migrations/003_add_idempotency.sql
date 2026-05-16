ALTER TABLE jobs
ADD COLUMN idempotency_key UUID NOT NULL;

CREATE UNIQUE INDEX idx_jobs_idempotency
ON jobs(tenant_id, idempotency_key);
