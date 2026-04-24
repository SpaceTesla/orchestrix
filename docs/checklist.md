## PHASE 1 — Synchronous Foundation

- [ ] Job dataclass with all required fields
- [ ] JobRunner with submit() and run_all()
- [ ] Status transitions work correctly
- [ ] Failed handlers mark jobs FAILED with error captured
- [ ] No global state

## PHASE 2 — Async Execution

- [ ] All handlers are async def
- [ ] asyncio.TaskGroup used for concurrent execution
- [ ] Semaphore limits concurrent jobs
- [ ] asyncio.timeout() kills slow handlers
- [ ] No blocking calls in async context

## PHASE 3 — Postgres Persistence

- [ ] jobs and job_events tables created
- [ ] asyncpg connection pool initialized
- [ ] Optimistic lock on status transitions
- [ ] Every transition writes to job_events
- [ ] TIMESTAMPTZ everywhere
- [ ] Indexes created and verified with EXPLAIN ANALYZE

## PHASE 4 — Redis Queue

- [ ] FastAPI submission endpoint
- [ ] Redis Streams with consumer groups
- [ ] Worker is a separate process
- [ ] XAUTOCLAIM handles dead consumer recovery
- [ ] Job payload in Postgres, only job_id in stream

## PHASE 5 — Multiple Workers

- [ ] 3 workers run simultaneously without duplicates
- [ ] Each worker has a unique worker_id
- [ ] Optimistic lock verified under concurrent workers
- [ ] Worker pause + XAUTOCLAIM recovery tested

## PHASE 6 — Rate Limiting

- [ ] Token bucket Lua script written and tested
- [ ] Script registered, not EVAL'd inline
- [ ] Tenant config cached with TTL
- [ ] Backoff with jitter when rate-limited
- [ ] Rate limit verified at correct RPS

## PHASE 7 — Multi-Tenancy and Failures

- [ ] Idempotency key deduplication working
- [ ] Three priority queues with weighted polling
- [ ] Retry with exponential backoff + jitter
- [ ] DEAD status after max_attempts
- [ ] Reaper recovers orphaned RUNNING jobs
- [ ] Reaper uses optimistic lock

## PHASE 8 — Observability

- [ ] structlog configured, all logs are JSON in prod
- [ ] Every worker log includes job_id, tenant_id, worker_id
- [ ] All 7 Prometheus metrics implemented
- [ ] Grafana dashboard with all required panels
- [ ] OpenTelemetry tracing spans full job lifecycle
- [ ] trace_id stored in Postgres, retrievable in Jaeger

## PHASE 9 — Load Testing

- [ ] All 4 Locust scenarios written and passing
- [ ] Graceful shutdown on SIGTERM tested
- [ ] Connection pool size tuned with evidence
- [ ] Redis kill + restart recovery tested
- [ ] Postgres kill + restart recovery tested
- [ ] Load test results (Grafana screenshots) in README

## PHASE 10 — Stretch Goals (Optional)

- [ ] Weighted Fair Queuing implemented
- [ ] Circuit breaker per job type
- [ ] Tenant control plane API with row-level security
