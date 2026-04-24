# ADR 0001 — Phase Guardrails: Why We Don't Skip Ahead

**Status:** Accepted  
**Date:** 2026-04-24  
**Context:** Pre-implementation, Phase 1 start

---

## Context

This project builds a distributed job execution engine across 10 phases. Each phase deliberately introduces one layer of complexity on top of the previous one. The temptation — especially with an AI assistant in the loop — is to jump ahead and add Redis, async, or Postgres before the simpler foundations are solid.

This ADR records why that would be a mistake, and locks in the rule.

---

## Decision

**No phase's tools, concepts, or libraries are introduced before their designated phase.**

Specific examples of what this means:

| Temptation | Why it's banned until its phase |
|---|---|
| Using `asyncio` in Phase 1 | Masks the synchronous state machine; you won't understand *why* async is needed until you've felt the blocking |
| Adding Postgres in Phase 1–2 | You won't appreciate durable state until you've lost in-memory state after a crash |
| Using Redis before Phase 4 | You won't understand *why* queues exist until submission and execution compete for the same thread |
| Using SQLAlchemy instead of raw `asyncpg` | ORM magic hides what Postgres is actually doing; you need to write raw SQL to understand query planning and transactions |
| Using an existing task queue (Celery, ARQ, etc.) | Defeats the entire purpose; the learning is in building these primitives |

---

## Consequences

**Good:**
- Each bug you hit is a distributed systems lesson, not a dependency mystery
- When you finish Phase 5 and truly understand why optimistic locking prevents double-execution, you'll be able to explain it in an interview from first principles
- The `docs/dev-notes.md` file becomes a real learning artifact, not a list of "I just followed the tutorial"

**Bad (acceptable):**
- Phase 1 code will be thrown away or significantly rewritten in Phase 3 — that's the point
- The `Job` dataclass you design in Phase 1 will turn out to be wrong for Postgres — you're supposed to discover that

---

## Technology Choices — Recorded Here for Future Phases

These decisions are pre-made to avoid re-litigating them mid-project:

### Queue: Redis Streams (not RabbitMQ, not Kafka, not Redis Lists)
- Consumer groups give at-least-once delivery with per-message acknowledgment
- `XAUTOCLAIM` handles dead consumer recovery without a separate mechanism
- Redis Lists don't have consumer groups — double-execution is trivially possible
- Kafka is operationally heavier than needed for this scale of learning project

### Rate Limiting: Token Bucket (not leaky bucket, not sliding window)
- Burst-aware — models real API behavior (burst then throttle)
- Implemented as a Redis Lua script for atomicity — two workers checking simultaneously still produce a correct result
- Simple enough to understand fully; complex enough to get wrong in interesting ways

### Concurrency Control: Optimistic Locking (not Redis SETNX, not SELECT FOR UPDATE)
- `UPDATE jobs SET status='running' WHERE id=$1 AND status='pending' RETURNING id` — single atomic operation
- No held locks, no deadlock risk
- A worker that loses the race gets zero rows back — explicit, not silent
- `SELECT FOR UPDATE SKIP LOCKED` is introduced in Phase 5 as an alternative to understand — but optimistic locking remains primary

### Async: `asyncio.TaskGroup` (not `asyncio.gather`)
- `TaskGroup` cancels all children when one raises — structured concurrency
- `gather()` swallows exceptions by default; `TaskGroup` propagates them correctly
- Python 3.11+ — matches the `requires-python = ">=3.13"` in `pyproject.toml`

### DB Client: `asyncpg` (not SQLAlchemy, not databases, not psycopg3)
- Raw SQL means you know exactly what queries run
- `asyncpg` is the fastest async Postgres driver for Python
- SQLAlchemy's ORM abstractions are valuable in production but are the enemy of learning at this stage

---

## Revisit Criteria

This ADR should be revisited only if:
1. A phase's constraint produces a bug that cannot be fixed without borrowing from a future phase (unlikely by design)
2. The project scope changes to "ship to production" rather than "learn by building"
