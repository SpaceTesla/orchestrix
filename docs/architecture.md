# Architecture

> This document reflects the system as it exists **right now** (through **Phase 6**). Update the "Current State" section at the start of each new phase.

---

## Current State — Phase 6 (Multi-worker + per-tenant rate limiting)

```
                   ┌─────────────────────┐
                   │   Client / curl     │
                   └──────────┬──────────┘
                              │ POST /jobs (tenant_id required)
                              ▼
                   ┌─────────────────────┐
                   │    FastAPI (API)    │
                   │ POST /jobs          │
                   │ GET /jobs/{id}      │
                   │ GET /jobs           │
                   └────┬───────────┬────┘
                        │           │
               write job│           │ XADD job_id only
               (PENDING)│           │
                        ▼           ▼
               ┌──────────────┐  ┌──────────────────────────────────┐
               │   Postgres   │  │            Redis                │
               │  jobs        │  │  Stream: jobs:queue             │
               │  job_events  │  │  Group: workers (per consumer)  │
               │  tenants     │  │  Cache: tenant_config:{tenant}  │
               └──────────────┘  │  Bucket: rate_limit:{tenant}    │
                        ▲        └──────────────┬───────────────────┘
                        │                       │ XREADGROUP / XAUTOCLAIM
                        │                       ▼
                        │   ┌───────────────────────────────────────┐
                        └───┤           Worker pool (N processes)      │
                            │  1) Read message (at-least-once)       │
                            │  2) Load job from Postgres              │
                            │  3) Tenant config (Redis cache → DB)  │
                            │  4) Rate limit gate (Lua token bucket)  │
                            │  5) Optimistic lock → RUNNING           │
                            │  6) Execute handler                     │
                            │  7) XACK stream message                 │
                            └───────────────────────────────────────────┘
```

**Implemented through Phase 6:**

- Postgres persistence with optimistic locking and `job_events` audit trail
- Redis Streams queue (`jobs:queue`) with consumer group `workers`
- Separate API and worker processes; scale workers via Compose (`--scale worker=N`)
- `XAUTOCLAIM` for reclaiming messages stuck in a consumer's PEL
- `tenants` table; every job has `tenant_id`
- Per-tenant token bucket in Redis (`rate_limit:{tenant_id}`), limits from `tenants` cached in Redis (`tenant_config:{tenant_id}`, 60s TTL)
- Backoff with jitter when rate-limited (`wait_until_allowed` + `sleep_retry_after_with_jitter`)

**What still does not exist yet (intentionally — Phase 7+):**

- Idempotency keys on `POST /jobs`
- Priority streams (`jobs:high` / `jobs:normal` / `jobs:low`) and weighted polling
- Retry with exponential backoff; `DEAD` after `max_attempts`
- Reaper for orphaned `RUNNING` jobs
- Transactional outbox / fix for Postgres-write-then-Redis-failure gap
- Observability stack (Phase 8): structured logging, Prometheus, OpenTelemetry

---

## Redis data model (Phase 6)

| Key | Type | Written by | Purpose |
|-----|------|------------|---------|
| `jobs:queue` | Stream | API (`XADD` on submit) | Work queue; payload is only `job_id` |
| `tenant_config:{tenant_id}` | Hash | Worker on cache miss | Cached `rate_limit_rps`, `burst_capacity` from Postgres; **TTL 60s** |
| `rate_limit:{tenant_id}` | Hash | Worker via Lua on each allow check | Token bucket state: `tokens`, `last_refill`; **TTL 3600s** (refreshed per check) |

**Important:** Rate limiting runs at **execution time** (worker), not on `POST /jobs`. The API does not touch `tenant_config` or `rate_limit` keys.

---

## Job State Machine

This state machine is the core invariant that must hold throughout all phases.

```
              submit()
                 │
                 ▼
            ┌─────────┐
            │ PENDING │◄──────────────────┐
            └────┬────┘                   │
                 │ worker claims          │ reaper (Phase 7)
                 ▼                        │ re-queues orphan
            ┌─────────┐                   │
            │ RUNNING │───────────────────┘
            └────┬────┘
                 │
        ┌────────┴────────┐
        │                 │
        ▼                 ▼
   ┌─────────┐      ┌────────┐
   │ SUCCESS │      │ FAILED │──► retry? ──► PENDING (Phase 7)
   └─────────┘      └────────┘
                        │
                    max_attempts
                    exceeded?
                        │
                        ▼
                   ┌────────┐
                   │  DEAD  │   (Phase 7)
                   └────────┘
```

**Key invariants:**

1. A job in `RUNNING` must eventually transition to `SUCCESS`, `FAILED`, or back to `PENDING` (via reaper — Phase 7)
2. No job should ever move backwards from `SUCCESS` or `DEAD`
3. `attempt_count` only ever increases
4. Every transition is recorded in `job_events` (Phase 3+)
5. Correctness under duplicate delivery comes from Postgres optimistic locking, not from the queue alone

---

## Target Architecture — Phase 7+ (not built yet)

The diagram below adds pieces planned for Phase 7 and beyond. **Do not assume these exist in the codebase until the checklist marks them done.**

```
                   ┌─────────────────────┐
                   │   Client / curl     │
                   └──────────┬──────────┘
                              │ POST /jobs
                              ▼
                   ┌─────────────────────┐
                   │    FastAPI (API)     │
                   │   POST /jobs        │
                   │   GET /jobs/{id}    │
                   └────┬───────────┬────┘
                        │           │
               write job│           │push job_id
               (PENDING)│           │XADD (priority stream)
                        ▼           ▼
               ┌──────────────┐  ┌──────────────┐
               │   Postgres   │  │    Redis      │
               │  jobs table  │  │  jobs:high    │
               │  job_events  │  │  jobs:normal  │
               │  tenants     │  │  jobs:low     │
               └──────────────┘  │  + rate limit │
                        ▲        │  + tenant cfg │
                        │        └──────┬─────────┘
                   read/│               │ XREADGROUP
                  update│               ▼
                        │   ┌───────────────────────┐
                        └───┤     Worker pool        │
                            │  + reaper coroutine    │
                            │  + retries / DEAD      │
                            │  + idempotency keys    │
                            └────────────────────────┘
```

---

## Component Responsibilities by Phase

| Component | Introduced | Responsibility |
|---|---|---|
| `JobRunner` (in-memory) | Phase 1 | Submit, execute, track state (learning scaffold; not production path) |
| `asyncio` + `TaskGroup` | Phase 2 | Concurrent execution, timeouts |
| Postgres `jobs` table | Phase 3 | Durable state store |
| Postgres `job_events` | Phase 3 | Append-only audit trail |
| Redis Streams | Phase 4 | Decouple submission from execution |
| FastAPI | Phase 4 | HTTP submission and status API |
| Worker process | Phase 4 | Standalone consumer process |
| Multiple workers | Phase 5 | Horizontal scale; races surfaced and handled via optimistic lock |
| Postgres `tenants` | Phase 6 | Per-tenant rate limit configuration |
| `TenantConfigCache` | Phase 6 | Redis cache of tenant limits (60s TTL) |
| Token bucket (Lua) | Phase 6 | Per-tenant execution rate limiting across all workers |
| `wait_until_allowed` + jitter backoff | Phase 6 | Block worker until bucket grants a token |
| Reaper coroutine | Phase 7 | Recover orphaned `RUNNING` jobs |
| Priority streams + weighted poll | Phase 7 | High/normal/low queue fairness |
| Idempotency keys | Phase 7 | Dedupe `POST /jobs` per tenant |
| `structlog` | Phase 8 | Structured JSON logging |
| Prometheus + Grafana | Phase 8 | Metrics and dashboards |
| OpenTelemetry + Jaeger | Phase 8 | Distributed tracing |
| Locust | Phase 9 | Load testing |

---

## Key Design Invariants (Hold Throughout All Phases)

1. **Job payload lives in Postgres** — only `job_id` travels through Redis Streams
2. **At-least-once delivery** is the baseline; optimistic locking makes duplicate delivery safe
3. **Every status transition is a single DB transaction** — `UPDATE jobs` + `INSERT job_events`
4. **Workers are stateless** — any worker can execute any job; shared rate-limit state lives in Redis
5. **The reaper uses the same optimistic lock** as workers — no special-casing (Phase 7)
6. **Rate limiting is enforced at execution time** (worker), not submission time (API)
7. **Tenant limits are authoritative in Postgres** — Redis `tenant_config` is a short-lived cache only

---

## What Intentionally Doesn't Exist

- No message broker (Kafka, RabbitMQ) — Redis Streams is sufficient for this project
- No ORM — raw `asyncpg` SQL so every query is explicit
- No Kubernetes — Docker Compose only
- No multi-region — single-region throughout
- No priority queues, reaper, or idempotency until Phase 7 (see checklist)
