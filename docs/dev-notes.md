# Dev Notes

A running log of discoveries, mistakes, and "aha" moments phase by phase.

> Write here while things are fresh. Future-you will thank you. These notes are also useful to review before jumping to the next phase — they reveal which concepts you actually internalized vs. just got to work.

---

## Format

Each entry:

```text
### [Phase N] Short title
Date: YYYY-MM-DD
What happened / what I learned / what tripped me up
```

---

# Phase 1 — Synchronous Foundation

_(Start adding notes here once you begin Phase 1)_

## Pre-phase question

Before starting Phase 1, try to answer these without looking anything up:

1. What fields does a `Job` actually need? What does a job need to _remember_ about itself?
2. What happens if `run_next()` is called and there are no pending jobs? How should it behave?
3. Why use `uuid.uuid4()` for job IDs instead of an auto-incrementing integer?
4. Why is `JobStatus.PENDING` better than the string `"pending"`?

Write your answers here first, then see if the code matches what you thought.

---

### [Phase 1] Jobs are basically state machines

Date: 2026-04-25

Initially I thought jobs were just payload + function execution, but I realized a job is fundamentally a state machine. A job needs to remember not only its payload, but also execution state, timestamps, and failure information.

I also realized why `started_at` and `completed_at` are separate fields. The gap between them represents execution duration and becomes useful later for timeouts, observability, retries, and orphan detection.

I learned why enums are better than raw strings for statuses. Enums reduce invalid states and make transitions easier to reason about.

Another important realization was why UUIDs are preferred over sequential IDs in distributed systems:

- workers can generate them independently
- avoids coordination bottlenecks
- harder to guess externally

Biggest takeaway:
A “job runner” is really a system that manages transitions between states.

---

### [Phase 1] Sequential execution hides system limitations

Date: 2026-04-25

While implementing synchronous execution, I noticed the entire system blocks while a single handler executes.

If one handler takes 30 seconds:

- the runner does nothing else
- throughput collapses
- no concurrency exists

This made the limitations of synchronous execution extremely obvious and naturally motivated Phase 2.

---

# Phase 2 — Async Execution

_(Populate when you reach Phase 2)_

## Pre-phase question

If `asyncio` runs on a single thread, how can multiple jobs run at the same time? What does "concurrent" actually mean here?

---

### [Phase 2] Async is cooperative multitasking, not magic parallelism

Date: 2026-04-26

At first I struggled to understand how asyncio could run multiple jobs on a single thread.

The key realization:
coroutines voluntarily yield execution at `await` points.

While one coroutine waits for I/O:

- another coroutine can run
- the thread itself is not blocked

This is concurrency, not true parallelism.

I also learned:

- `time.sleep()` blocks the entire event loop
- `asyncio.sleep()` yields control back to the scheduler

One accidental blocking call can freeze all concurrent jobs.

---

### [Phase 2] Semaphores control pressure, not correctness

Date: 2026-04-26

I initially thought semaphores were just concurrency helpers, but they are actually a form of backpressure.

Without a semaphore:

- every job launches immediately
- resource usage becomes uncontrolled

With a semaphore:

- execution throughput becomes bounded
- worker pressure becomes predictable

I also learned the semaphore must be acquired INSIDE the task, otherwise tasks accidentally serialize.

---

### [Phase 2] TaskGroup semantics were confusing initially

Date: 2026-04-26

I learned that `asyncio.TaskGroup` behaves differently from `gather()`.

Unhandled exceptions inside a TaskGroup can cancel sibling tasks. Structured concurrency forces tasks to fail together unless errors are handled intentionally.

This was initially confusing but later made sense because it prevents silent task leaks.

---

# Phase 3 — Postgres Persistence

_(Populate when you reach Phase 3)_

## Pre-phase question

Your Phase 1 `Job` dataclass had certain fields. Which of those will map cleanly to Postgres columns? Which ones are wrong or need to change? Why?

---

### [Phase 3] In-memory state is a lie

Date: 2026-04-26

The biggest realization of this phase:
memory is not truth.

The moment I moved jobs into Postgres, I started thinking differently about durability and ownership.

If the process dies:

- memory disappears
- Postgres survives

This fundamentally changes system design.

I also realized why append-only event tables are valuable:
they create an audit trail and make it possible to reconstruct job history later.

---

### [Phase 3] Optimistic locking is distributed compare-and-swap

Date: 2026-04-26

The optimistic lock initially looked deceptively simple:

```sql
UPDATE jobs
SET status='running'
WHERE id=$1
AND status='pending'
RETURNING id
```

But this became one of the most important concepts in the project.

The database itself becomes the concurrency coordinator.

If two workers race:

- one UPDATE succeeds
- one UPDATE returns zero rows

No explicit lock manager is needed.

This was my first real understanding of distributed mutual exclusion.

---

### [Phase 3] Transactions matter more than I expected

Date: 2026-04-26

I underestimated how important transactions are.

A job transition and event insertion must happen atomically.

Without a transaction:

- status could update
- event insert could fail
- system state becomes inconsistent

I also learned:
`asyncpg` auto-begins transactions but does not auto-commit them.

---

### [Phase 3] TIMESTAMPTZ is mandatory in distributed systems

Date: 2026-04-26

I finally understood why timezone-naive timestamps are dangerous.

Distributed systems may have:

- multiple machines
- different regions
- different timezones

Using `TIMESTAMPTZ` normalizes time handling and prevents subtle ordering bugs.

---

# Phase 4 — Redis Queue

_(Populate when you reach Phase 4)_

## Pre-phase question

What happens between the moment `POST /jobs` returns and the moment a worker starts executing the job? Who holds the job during that window?

---

### [Phase 4] Submission and execution are separate concerns

Date: 2026-05-07

This phase fundamentally changed how I think about backend systems.

The API does not execute jobs anymore.
It only:

- validates requests
- persists state
- enqueues references

Workers independently execute later.

This decoupling allows:

- buffering
- scalability
- independent failure handling

I finally understood why queues are such an important architectural pattern.

---

### [Phase 4] Redis Streams are much more sophisticated than simple queues

Date: 2026-05-07

Initially I thought Redis Streams were just fancy lists.

But consumer groups introduce:

- ownership
- pending tracking
- acknowledgements
- recovery

The Pending Entries List (PEL) became one of the most important concepts.

Redis essentially tracks:
“I delivered this message but completion was never confirmed.”

---

### [Phase 4] At-least-once delivery changes everything

Date: 2026-05-07

I learned that distributed queues prioritize durability over uniqueness.

Messages may be delivered multiple times.
Exactly-once delivery is extremely difficult.

This means correctness must come from:

- idempotency
- optimistic locking
- careful ownership transitions

not from the queue itself.

---

# Phase 5 — Multiple Workers

_(Populate when you reach Phase 5)_

## Pre-phase question

You have 3 workers and 1 job. All 3 workers see the job as `PENDING` at the same millisecond. Without any locking mechanism, what happens? Walk through it step by step.

---

### [Phase 5] Redis handles delivery coordination, not correctness

Date: 2026-05-11

When I first scaled to multiple workers, everything looked deceptively safe.

Redis consumer groups distributed jobs cleanly across workers, so initially I did not understand where race conditions would happen.

The major realization:
Redis Streams solve message routing, not execution correctness.

Correctness still belongs to:

- Postgres
- optimistic locking
- ownership validation

This distinction became one of the most important lessons of the project.

---

### [Phase 5] I finally understood at-least-once delivery

Date: 2026-05-11

I paused a worker while it was processing a job.

What happened:

- worker received message
- worker transitioned job to RUNNING
- worker froze before XACK
- Redis kept message in the PEL
- another worker reclaimed it using XAUTOCLAIM
- same message got delivered again

This was the first time I truly saw at-least-once delivery behavior in practice.

---

### [Phase 5] Optimistic locking prevented duplicate execution

Date: 2026-05-11

After reclaiming the stuck message, another worker attempted to execute the same job.

The optimistic lock prevented corruption.

The second worker attempted:

```sql
UPDATE jobs
SET status='running'
WHERE id=$1
AND status='pending'
RETURNING id
```

But because the first worker had already transitioned the job:

- UPDATE returned zero rows
- second worker lost the race
- duplicate execution was prevented

This was probably the biggest “aha” moment so far.

---

### [Phase 5] Safety and liveness are different problems

Date: 2026-05-11

The paused worker experiment revealed an important distinction.

The system achieved:

- safety (job did not execute twice)

But failed at:

- liveness (job never completed)

The job remained stuck in RUNNING forever because the original worker disappeared after ownership transfer.

This helped me understand why reapers/orphan recovery mechanisms exist.

---

# Phase 6 — Rate Limiting

_(Populate when you reach Phase 6)_

## Pre-phase question

Two workers call the token bucket Lua script simultaneously for the same tenant. Redis is single-threaded. What actually happens? In what order?

---

### [Phase 6] Redis serializes scripts; "simultaneous" becomes a strict queue

Date: 2026-05-14

The pre-phase question is a good sanity check.

Two clients can issue `EVALSHA` at the same wall-clock instant on the network, but Redis executes commands one at a time per shard. Each script run is atomic: refill from elapsed time, compare to `tokens_requested`, update hash fields, set key TTL, return `{allowed, remaining, retry_after}` with no interleaving from other commands.

So there is no undefined interleaving order inside the bucket for a single key; the meaningful "order" is whatever order Redis accepted the connections' bytes.

---

### [Phase 6] `register_script` is the real "no inline EVAL" win

Date: 2026-05-14

`RedisRateLimiter` loads `token_bucket.lua` once at construction and calls `redis.register_script`. After that, the client sends the script body to Redis only until the server has cached the SHA; later calls use `EVALSHA` semantics instead of shipping the full Lua on every request.

That matches the checklist intent: register once, execute many times, not giant `EVAL` payloads per allow check.

---

### [Phase 6] Token bucket state is a tiny hash, not a queue

Date: 2026-05-14

The Lua script stores `tokens` and `last_refill` in a Redis hash keyed by tenant (`rate_limit:{tenant_id}`). Refill is continuous: `elapsed * refill_rate`, capped at `max_tokens`, then debit if allowed.

On deny, it still advances `last_refill` to `current_time` (passed from Python as `time.time()`), which matches classic token-bucket semantics and yields a deterministic `retry_after` hint when `refill_rate > 0`. When `refill_rate == 0`, the script returns `retry_after = -1` so callers know there is no time-based refill.

The bucket key also gets a one-hour `EXPIRE` so idle tenants do not accumulate state forever.

---

### [Phase 6] Tenant limits live in Postgres; Redis is a short TTL mirror

Date: 2026-05-14

`TenantConfigCache` reads `tenant_config:{tenant_id}` as a Redis hash. On miss it loads `rate_limit_rps` and `burst_capacity` from `tenants`, writes the hash back, and sets `EXPIRE` to 60 seconds (`CACHE_TTL_SECONDS`).

So rate limit parameters are authoritative in Postgres, but hot paths avoid hitting the DB on every job once the tenant is warm.

---

### [Phase 6] Jitter belongs in application code, not in Lua

Date: 2026-05-14

`sleep_retry_after_with_jitter` adds a small uniform jitter on top of `retry_after` (and a fixed floor when `retry_after < 0`) so many workers do not wake up in lockstep and hammer Redis.

The Lua stays deterministic, which keeps the script easy to reason about and test; `scripts/test_lua.py` exercises concurrent `allow()` calls, and `scripts/test_rate_limit_backoff.py` spins many async workers to confirm bounded retries without busy-spin.

---

# Phase 7 — Multi-Tenancy and Failures

_(Populate when you reach Phase 7)_

---

### [Phase 7] Placeholder

Date: YYYY-MM-DD

TODO

---

# Phase 8 — Observability

_(Populate when you reach Phase 8)_

---

### [Phase 8] Placeholder

Date: YYYY-MM-DD

TODO

---

# Phase 9 — Load Testing

_(Populate when you reach Phase 9)_

---

### [Phase 9] Placeholder

Date: YYYY-MM-DD

TODO

---

# Things I Got Wrong (Running List)

_(Add here as you go — this is the most valuable section)_

| Phase | What I assumed                                        | What actually happened                                         | What I learned                                                |
| ----- | ----------------------------------------------------- | -------------------------------------------------------------- | ------------------------------------------------------------- |
| 2     | asyncio gives parallelism                             | asyncio gives cooperative concurrency                          | Await points are what allow task switching                    |
| 2     | `time.sleep()` inside async code is harmless          | it blocks the entire event loop                                | blocking calls freeze all coroutines                          |
| 3     | DB state changes are simple updates                   | distributed ownership depends on atomic transitions            | transactions and optimistic locks are critical                |
| 4     | queues guarantee uniqueness                           | Redis Streams guarantee at-least-once delivery                 | correctness must exist outside the queue                      |
| 5     | Redis consumer groups prevent all races               | reclaim/re-delivery still creates duplicate delivery scenarios | DB optimistic locking is the real correctness layer           |
| 5     | preventing duplicate execution means system is solved | jobs can still become orphaned forever                         | safety and liveness are separate distributed systems concerns |
| 6     | rate-limit randomness should live in Redis            | Lua returns a deterministic `retry_after`; Python adds jitter | keep scripts testable; spread wakeups in the client               |
| 6     | every allow check should hit Postgres for limits      | tenant config is cached in Redis with TTL on miss              | separate source of truth (DB) from read path amplification       |

---

# Concepts I Had to Look Up More Than Once

_(If you looked something up twice, write a one-line summary here so you don't look it up a third time)_

| Concept                    | One-line summary                                                                     |
| -------------------------- | ------------------------------------------------------------------------------------ |
| asyncio.TaskGroup          | Structured concurrency primitive where sibling task failures propagate intentionally |
| Optimistic locking         | Distributed compare-and-swap using conditional UPDATE statements                     |
| Pending Entries List (PEL) | Redis Streams structure tracking delivered-but-unacked messages                      |
| XAUTOCLAIM                 | Redis Streams command used to reclaim abandoned pending messages                     |
| At-least-once delivery     | Messages may be delivered multiple times and systems must tolerate duplicates        |
| TIMESTAMPTZ                | Timezone-aware timestamps required for distributed systems correctness               |
| Structured concurrency     | Tasks should have explicit ownership/lifecycle relationships                         |
| Safety vs liveness         | Preventing corruption is separate from guaranteeing eventual completion              |
| `register_script` (redis-py) | Load Lua once; server caches SHA; hot path uses `EVALSHA`-style execution, not full `EVAL` each time |
| Token bucket in Redis      | Hash holds tokens + last refill; script refills by elapsed time, caps burst, debits atomically per call |
