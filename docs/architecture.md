# Architecture

> This document reflects the system as it exists **right now** (through **Phase 7**). Update the "Current State" section at the start of each new phase.

---

## Current State — Phase 7 (Multi-tenancy, priority, retries, reaper)

```
                   ┌─────────────────────┐
                   │   Client / curl     │
                   └──────────┬──────────┘
                              │ POST /jobs (tenant_id + Idempotency-Key)
                              ▼
                   ┌─────────────────────┐
                   │    FastAPI (API)    │
                   │ POST /jobs          │
                   │ GET /jobs/{id}      │
                   │ GET /jobs           │
                   └────┬───────────┬────┘
                        │           │
               write job│           │ XADD job_id (priority stream)
               (PENDING)│           │
                        ▼           ▼
               ┌──────────────┐  ┌──────────────────────────────────┐
               │   Postgres   │  │            Redis                │
               │  jobs        │  │  jobs:high / jobs:normal / low  │
               │  job_events  │  │  Group: workers (per consumer)  │
               │  tenants     │  │  Cache: tenant_config:{tenant}  │
               └──────────────┘  │  Bucket: rate_limit:{tenant}    │
                        ▲        └──────────────┬───────────────────┘
                        │                       │ XREADGROUP / XAUTOCLAIM
                        │                       ▼
                        │   ┌───────────────────────────────────────┐
                        └───┤     Worker pool (N processes each)     │
                            │  + reaper coroutine (orphan recovery)  │
                            │  1) Read message (weighted poll)       │
                            │  2) Load job; wait until scheduled_at  │
                            │  3) Rate limit gate (Lua token bucket) │
                            │  4) Optimistic lock → RUNNING          │
                            │  5) Execute handler (timeout)          │
                            │  6) SUCCESS / retry / DEAD + re-enqueue│
                            │  7) XACK stream message                │
                            └────────────────────────────────────────┘
```

**Implemented through Phase 7:**

- Everything from Phase 6 (Postgres, Redis Streams, multi-worker, per-tenant rate limiting)
- **Idempotency:** `Idempotency-Key` header (UUID); unique per `(tenant_id, idempotency_key)`; duplicate POST returns **200** with existing job
- **Priority queues:** `jobs:high`, `jobs:normal`, `jobs:low`; worker **weighted poll** (5:3:1); enqueue on create, retry, and reaper reclaim
- **Retries:** exponential backoff + jitter; `scheduled_at` for delayed eligibility; `retry_scheduled` / `job_dead` events
- **DEAD:** terminal status when `attempt_count >= max_attempts` (handler failure or reaper)
- **Reaper:** background coroutine per worker; stale `RUNNING` jobs reclaimed with optimistic `UPDATE`; `reaped` events; `reaper_threshold_seconds` > `job_timeout_seconds` (validated at startup)
- **Handler registry:** `job_type` → async handler (`handlers/registry.py`)

**What still does not exist yet (intentionally — Phase 8+):**

- Transactional outbox / fix for Postgres-write-then-Redis-failure gap
- Observability stack (Phase 8): structured logging, Prometheus, OpenTelemetry
- Load testing harness (Phase 9)

---

## Redis data model (Phase 7)

| Key | Type | Written by | Purpose |
|-----|------|------------|---------|
| `jobs:high` | Stream | API, worker (retry/reaper) | High-priority work queue; payload is only `job_id` |
| `jobs:normal` | Stream | API, worker (retry/reaper) | Normal-priority work queue |
| `jobs:low` | Stream | API, worker (retry/reaper) | Low-priority work queue |
| `tenant_config:{tenant_id}` | Hash | Worker on cache miss | Cached `rate_limit_rps`, `burst_capacity`; **TTL 60s** |
| `rate_limit:{tenant_id}` | Hash | Worker via Lua | Token bucket state; **TTL 3600s** |

**Important:** Rate limiting runs at **execution time** (worker), not on `POST /jobs`.

---

## Job State Machine

```
              submit()
                 │
                 ▼
            ┌─────────┐
            │ PENDING │◄────────────────────────┐
            └────┬────┘                         │
                 │ worker claims                 │ retry / reaper
                 ▼                               │
            ┌─────────┐──────────────────────────┘
            │ RUNNING │
            └────┬────┘
                 │
        ┌────────┼────────┐
        │        │        │
        ▼        ▼        ▼
   ┌─────────┐  retry   ┌────────┐
   │ SUCCESS │  pending  │  DEAD  │
   └─────────┘           └────────┘
```

Worker path on handler failure: `running` → `pending` (retry) or `dead` (exhausted). The `failed` enum value remains in Postgres for schema compatibility but is not used on the hot path.

**Key invariants:**

1. A job in `RUNNING` must eventually reach `SUCCESS`, `DEAD`, or return to `PENDING` (retry or reaper)
2. No job moves backwards from `SUCCESS` or `DEAD`
3. `attempt_count` only increases (on claim to `RUNNING`, and again on reaper reclaim)
4. Every meaningful transition is recorded in `job_events`
5. Duplicate delivery is safe via optimistic locking on status transitions
6. `reaper_threshold_seconds` must be **greater than** `job_timeout_seconds`

---

## Component Responsibilities by Phase

| Component | Introduced | Responsibility |
|---|---|---|
| `JobRunner` (in-memory) | Phase 1 | Learning scaffold; mirrors retry/DEAD semantics |
| `asyncio` + `TaskGroup` | Phase 2 | Concurrent execution, timeouts |
| Postgres `jobs` table | Phase 3 | Durable state store |
| Postgres `job_events` | Phase 3 | Append-only audit trail |
| Redis Streams | Phase 4 | Decouple submission from execution |
| FastAPI | Phase 4 | HTTP submission and status API |
| Worker process | Phase 4 | Standalone consumer process |
| Multiple workers | Phase 5 | Horizontal scale; optimistic lock |
| Postgres `tenants` | Phase 6 | Per-tenant rate limit configuration |
| `TenantConfigCache` | Phase 6 | Redis cache of tenant limits (60s TTL) |
| Token bucket (Lua) | Phase 6 | Per-tenant execution rate limiting |
| Priority streams + weighted poll | Phase 7 | High/normal/low queue fairness |
| Idempotency keys | Phase 7 | Dedupe `POST /jobs` per tenant |
| Retry + backoff + `DEAD` | Phase 7 | Resilient failure handling |
| Reaper coroutine | Phase 7 | Recover orphaned `RUNNING` jobs |
| Handler registry | Phase 7 | Dispatch `job_type` to handlers |
| `structlog` | Phase 8 | Structured JSON logging |
| Prometheus + Grafana | Phase 8 | Metrics and dashboards |
| OpenTelemetry + Jaeger | Phase 8 | Distributed tracing |
| Locust | Phase 9 | Load testing |

---

## Key Design Invariants (Hold Throughout All Phases)

1. **Job payload lives in Postgres** — only `job_id` travels through Redis Streams
2. **At-least-once delivery** is the baseline; optimistic locking makes duplicate delivery safe
3. **Every status transition is a single DB transaction** — `UPDATE jobs` + `INSERT job_events`
4. **Workers are stateless** — shared rate-limit state lives in Redis
5. **The reaper uses the same optimistic lock pattern** as workers (`WHERE status = 'running'`)
6. **Rate limiting is enforced at execution time** (worker), not submission time (API)
7. **Tenant limits are authoritative in Postgres** — Redis `tenant_config` is a short-lived cache only
8. **Handlers should be idempotent** — reaper and at-least-once delivery can cause duplicate execution

---

## What Intentionally Doesn't Exist

- No message broker (Kafka, RabbitMQ) — Redis Streams is sufficient for this project
- No ORM — raw `asyncpg` SQL so every query is explicit
- No Kubernetes — Docker Compose only
- No multi-region — single-region throughout
- No transactional outbox yet — rare Postgres-without-Redis enqueue gap remains
- No observability stack until Phase 8 (see checklist)
