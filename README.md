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

**Phase 6 — Rate limiting (per-tenant token bucket)**

FastAPI accepts job submissions (with `tenant_id`), persists jobs to Postgres, and enqueues `job_id` into a Redis Stream.
One or more worker processes consume the stream, enforce per-tenant limits via a Redis Lua token bucket, then claim and execute jobs in Postgres.

Progress: see [`docs/checklist.md`](docs/checklist.md). Architecture: [`docs/architecture.md`](docs/architecture.md).

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

# Run API
uv run orchestrix api --reload

# In another terminal: run worker(s)
uv run orchestrix worker

# Or via Docker Compose (Postgres + Redis + API + 3 workers)
docker compose -f compose.yaml -f compose.dev.yaml up --build --scale worker=3

# Unit tests (Phase 7 pure logic; no Postgres/Redis required)
uv sync --group dev
uv run pytest

# Same tests inside the API container (requires compose.dev.yaml tests mount)
docker compose -f compose.yaml -f compose.dev.yaml exec api sh -c "uv sync --group dev && uv run pytest"
```

Example request (requires a tenant in Postgres — run `scripts/bootstrap_db.py` and seed via `scripts/seed_jobs.py`, or use your tenant UUID):

```bash
curl -X POST http://127.0.0.1:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"<uuid>","job_type":"test","payload":{"hello":"world"}}'
```

---

## Project Structure

```
orchestrix/
  src/orchestrix/
    api/               # FastAPI app (Phase 4+)
    worker/            # Worker process (Phase 4+)
    db/                # asyncpg pool + queries + migrations (Phase 3+)
    queue/             # Redis Streams client (Phase 4+)
    cache/             # Tenant config Redis cache (Phase 6)
    rate_limit/        # Token bucket Lua + gate + backoff (Phase 6)
    runner/            # In-memory JobRunner (Phase 1–2 learning scaffold)
    main.py            # CLI entrypoint (api/worker)
  scripts/             # DB bootstrap, seed_jobs, rate-limit tests
  docs/                # Roadmap, architecture, checklist, dev-notes
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

- If Postgres write succeeds but Redis `XADD` fails, the job stays `pending` in Postgres with no stream message (addressed in Phase 7)
- No idempotency keys, priority queues, automatic retries, or reaper yet (Phase 7)
- Single stream `jobs:queue` only (not `jobs:high` / `normal` / `low`)
- Single-region only, no HA Postgres
- No structured metrics/tracing yet (Phase 8)
- No authentication until Phase 10 stretch goal
- Local Docker Compose only — no Kubernetes / cloud deployment

---

## Load Test Results

*(Populated in Phase 9)*

---

## What the Reaper Does

*(Populated in Phase 7)*

---

## Why the Lua Script Must Be Atomic

Multiple workers can call the rate limiter for the same tenant at the same time. Redis runs each Lua script atomically: read bucket state, refill by elapsed time, debit a token (or deny), write state, and return — with no interleaving from other commands. A non-atomic read-modify-write in Python would let two workers both think a token is available. See `src/orchestrix/rate_limit/lua/token_bucket.lua` and [`docs/architecture.md`](docs/architecture.md#redis-data-model-phase-6).
