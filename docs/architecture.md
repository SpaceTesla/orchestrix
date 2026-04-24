# Architecture

> This document reflects the system as it exists **right now** (Phase 1) and projects forward to the target state. Update the "Current State" section at the start of each new phase.

---

## Current State — Phase 1 (Synchronous, In-Memory)

```
┌─────────────────────────────────┐
│           JobRunner             │
│                                 │
│  jobs: list[Job]  (in-memory)   │
│                                 │
│  submit(job_type, payload)      │
│      └─► append Job(PENDING)    │
│                                 │
│  run_next()                     │
│      └─► pick first PENDING     │
│          run handler            │
│          update status          │
│                                 │
│  run_all()                      │
│      └─► loop until no PENDING  │
└─────────────────────────────────┘
```

**What doesn't exist yet (intentionally):**
- No persistence — all state dies with the process
- No HTTP API
- No concurrency
- No external dependencies

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
                 │ run_next() picks it     │ reaper (Phase 7)
                 ▼                        │ re-queues orphan
            ┌─────────┐                   │
            │ RUNNING │───────────────────┘
            └────┬────┘
                 │
        ┌────────┴────────┐
        │                 │
        ▼                 ▼
   ┌─────────┐      ┌────────┐
   │ SUCCESS │      │ FAILED │──► retry? ──► PENDING (attempt_count++)
   └─────────┘      └────────┘
                        │
                    max_attempts
                    exceeded?
                        │
                        ▼
                   ┌────────┐
                   │  DEAD  │   (no more retries)
                   └────────┘
```

**Key invariants:**
1. A job in `RUNNING` must eventually transition to `SUCCESS`, `FAILED`, or back to `PENDING` (via reaper)
2. No job should ever move backwards from `SUCCESS` or `DEAD`
3. `attempt_count` only ever increases
4. Every transition is recorded in `job_events` (Phase 3+)

---

## Target Architecture — Phase 4+ (Distributed)

This is where the system is heading. Build toward it phase by phase.

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
               (PENDING)│           │XADD
                        ▼           ▼
               ┌──────────────┐  ┌──────────────┐
               │   Postgres   │  │    Redis      │
               │  jobs table  │  │  Streams      │
               │  job_events  │  │  jobs:high    │
               │  tenants     │  │  jobs:normal  │
               └──────────────┘  │  jobs:low     │
                        ▲        └──────┬─────────┘
                        │               │ XREADGROUP
                   read/│               ▼
                  update│   ┌───────────────────────┐
                        │   │     Worker Pool        │
                        │   │  ┌───────┐ ┌───────┐  │
                        └───┤  │  W1   │ │  W2   │  │
                            │  └───────┘ └───────┘  │
                            │  ┌───────┐ ┌───────┐  │
                            │  │  W3   │ │ ...   │  │
                            │  └───────┘ └───────┘  │
                            │                        │
                            │  Each worker:          │
                            │  1. Read from stream   │
                            │  2. Check rate limit   │
                            │     (Lua/Redis)        │
                            │  3. Optimistic lock    │
                            │     (Postgres)         │
                            │  4. Execute handler    │
                            │  5. XACK message       │
                            └────────────────────────┘
```

---

## Component Responsibilities by Phase

| Component | Introduced | Responsibility |
|---|---|---|
| `JobRunner` (in-memory) | Phase 1 | Submit, execute, track state |
| `asyncio` + `TaskGroup` | Phase 2 | Concurrent execution, timeouts |
| Postgres `jobs` table | Phase 3 | Durable state store |
| Postgres `job_events` | Phase 3 | Append-only audit trail |
| Redis Streams | Phase 4 | Decouple submission from execution |
| FastAPI | Phase 4 | HTTP submission and status API |
| Worker process | Phase 4 | Standalone consumer process |
| Multiple workers | Phase 5 | Horizontal scale; concurrency bugs surface |
| Token bucket (Lua) | Phase 6 | Per-tenant rate limiting |
| Reaper coroutine | Phase 7 | Recover orphaned `RUNNING` jobs |
| `structlog` | Phase 8 | Structured JSON logging |
| Prometheus + Grafana | Phase 8 | Metrics and dashboards |
| OpenTelemetry + Jaeger | Phase 8 | Distributed tracing |
| Locust | Phase 9 | Load testing |

---

## Key Design Invariants (Hold Throughout All Phases)

1. **Job payload lives in Postgres** — only `job_id` travels through Redis
2. **At-least-once delivery** is the baseline; idempotency (optimistic lock) makes it safe
3. **Every status transition is a single DB transaction** — `UPDATE jobs` + `INSERT job_events`
4. **Workers are stateless** — any worker can execute any job
5. **The reaper uses the same optimistic lock** as workers — no special-casing
6. **Rate limiting is enforced at execution time** (worker), not submission time (API)

---

## What Intentionally Doesn't Exist

- No message broker (Kafka, RabbitMQ) — Redis Streams is sufficient and simpler to reason about
- No ORM — raw `asyncpg` SQL so every query is explicit and learnable
- No Kubernetes — Docker Compose only; the learning is in the logic, not the infra
- No multi-region — single-region throughout this project
