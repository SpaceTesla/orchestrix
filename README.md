# Orchestrix

A distributed, rate-limited job execution engine — built phase by phase as a learning project.

> This is not a "ship it fast" project. The goal is to deeply understand distributed systems, async execution, queuing, rate limiting, and failure handling by building each layer from scratch.

---

## What This Is

Orchestrix is a job execution system that evolves across 10 phases:

```
Phase 1  →  Sync runner in memory
Phase 2  →  Async runner with asyncio
Phase 3  →  Postgres (persistent state machine)
Phase 4  →  Redis queue (decouple submission from execution)
Phase 5  →  Multiple workers (watch things break)
Phase 6  →  Rate limiting (token bucket, per-tenant)
Phase 7  →  Multi-tenancy, priority queues, retries, reaper
Phase 8  →  Observability (logging, metrics, tracing)
Phase 9  →  Load testing and hardening
Phase 10 →  Stretch goals (WFQ, circuit breakers, control plane)
```

See [`docs/roadmap.md`](docs/roadmap.md) for the full phase-by-phase specification.

---

## Current Phase

**Phase 4 — Redis Queue (decouple submission from execution)**

FastAPI accepts job submissions, persists jobs to Postgres, and enqueues `job_id` into a Redis Stream.
A separate worker process consumes the stream and updates job status in Postgres.

---

## Running Locally

**Requirements:** Python 3.13+, [`uv`](https://github.com/astral-sh/uv)

```bash
# Clone and set up
git clone <repo-url>
cd orchestrix
cp .env.example .env
uv sync

# Ensure Postgres + Redis are running (example via Docker)
docker run --name orchestrix-postgres -e POSTGRES_PASSWORD=change-me -e POSTGRES_USER=orchestrix -e POSTGRES_DB=orchestrix -p 5432:5432 -d postgres:16
docker run --name orchestrix-redis -p 6379:6379 -d redis:7

# Bootstrap DB schema (Phase 3+)
uv run python scripts/bootstrap_db.py

# Run API (Phase 4)
uv run orchestrix api --reload

# In another terminal: run worker (Phase 4)
uv run orchestrix worker
```

Example request:

```bash
curl -X POST http://127.0.0.1:8000/jobs -H "Content-Type: application/json" -d "{\"job_type\":\"test\",\"payload\":{\"hello\":\"world\"}}"
```

---

## Project Structure

```
orchestrix/
  src/orchestrix/
    api/               # FastAPI app (Phase 4+)
    worker/            # Worker process (Phase 4+)
    db/                # asyncpg pool + queries (Phase 3+)
    queue/             # Redis Streams client (Phase 4+)
    main.py            # CLI entrypoint (api/worker)
  scripts/             # DB bootstrap and helpers
  docs/                # Roadmap + notes
  pyproject.toml       # Dependencies + console script
```

---

## Design Decisions

See [`docs/decisions/`](docs/decisions/) for ADRs.

Key choices at the Phase 6+ level:

| Decision | Choice | Why |
|---|---|---|
| Queue | Redis Streams | Consumer groups give at-least-once delivery with acknowledgment; Lists don't |
| Rate limiting | Token bucket (Lua, atomic) | Burst-aware; Lua atomicity avoids race conditions between workers |
| State store | Postgres | Durable truth; in-memory state is a lie in production |
| Concurrency control | Optimistic lock (`UPDATE ... WHERE status=... RETURNING id`) | No held locks; handles multi-worker races cleanly |
| Async runtime | `asyncio` + `TaskGroup` | Structured concurrency; better error propagation than `gather()` |

---

## Known Limitations

- Phase 4: if Postgres write succeeds but Redis `XADD` fails, the job will remain `pending` in Postgres but never be executed (fixed in Phase 7)
- Phase 3–5: single-region only, no HA Postgres
- No authentication until Phase 10 stretch goal
- No Kubernetes / cloud deployment — local Docker Compose only

---

## Load Test Results

*(Populated in Phase 9)*

---

## What the Reaper Does

*(Populated in Phase 7)*

---

## Why the Lua Script Must Be Atomic

*(Populated in Phase 6)*
