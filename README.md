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

**Phase 1 — Synchronous Foundation**

In-memory job runner. No database, no queue, no async. Just a clean state machine loop.

What exists right now:
- `Job` dataclass with status transitions
- `JobRunner` with `submit()`, `run_next()`, `run_all()`
- A small set of fake job handlers

What is intentionally NOT here yet:
- No HTTP API
- No database
- No Redis
- No concurrency

---

## Running Locally

**Requirements:** Python 3.13+, [`uv`](https://github.com/astral-sh/uv)

```bash
# Clone and set up
git clone <repo-url>
cd orchestrix
uv sync

# Run Phase 1
uv run python main.py
```

No Docker needed until Phase 3.

---

## Project Structure

```
orchestrix/
  main.py              # Current entrypoint
  docs/
    roadmap.md         # The master spec — your source of truth
    architecture.md    # System design, current state + future
    dev-notes.md       # Running log of discoveries and pitfalls
    decisions/
      0001-phase-guardrails.md   # Why we don't skip phases
  pyproject.toml
```

Structure will evolve to match the Phase 4 layout:

```
job_engine/
  api/         # FastAPI app (Phase 4+)
  worker/      # Worker process (Phase 4+)
  db/          # asyncpg pool and queries (Phase 3+)
  queue/       # Redis client (Phase 4+)
  models.py
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

- Phase 1–2: all state is lost on process restart (intentional)
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
