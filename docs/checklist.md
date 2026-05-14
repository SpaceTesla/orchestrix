## PHASE 1 — Synchronous Foundation

- [x] Job dataclass with all required fields
- [x] JobRunner with submit() and run_all()
- [x] Status transitions work correctly
- [x] Failed handlers mark jobs FAILED with error captured
- [x] No global state

## PHASE 2 — Async Execution

- [x] All handlers are async def
- [x] asyncio.TaskGroup used for concurrent execution
- [x] Semaphore limits concurrent jobs
- [x] asyncio.timeout() kills slow handlers
- [x] No blocking calls in async context

## PHASE 3 — Postgres Persistence

- [x] jobs and job_events tables created
- [x] asyncpg connection pool initialized
- [x] Optimistic lock on status transitions
- [x] Every transition writes to job_events
- [x] TIMESTAMPTZ everywhere
- [x] Indexes created and verified with EXPLAIN ANALYZE

## PHASE 4 — Redis Queue

- [x] FastAPI submission endpoint
- [x] Redis Streams with consumer groups
- [x] Worker is a separate process
- [x] XAUTOCLAIM handles dead consumer recovery
- [x] Job payload in Postgres, only job_id in stream

## PHASE 5 — Multiple Workers

- [x] 3 workers run simultaneously without duplicates
- [x] Each worker has a unique worker_id
- [x] Optimistic lock verified under concurrent workers
- [x] Worker pause + XAUTOCLAIM recovery tested

## PHASE 6 — Rate Limiting

- [x] Token bucket Lua script written and tested
- [x] Script registered, not EVAL'd inline
- [x] Tenant config cached with TTL
- [x] Backoff with jitter when rate-limited
- [x] Rate limit verified at correct RPS

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
