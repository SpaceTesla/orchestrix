# Master Execution Roadmap
## Distributed Rate-Limited Job Execution Engine

> This document is your single source of truth. Follow it phase by phase.
> Do not skip ahead. The pain you feel in each phase is the learning.

---

## System Evolution Map

```
Phase 1  →  Sync runner in memory
Phase 2  →  Async runner with asyncio
Phase 3  →  Add Postgres (persistent state machine)
Phase 4  →  Add Redis queue (decouple submission from execution)
Phase 5  →  Run multiple workers (watch things break)
Phase 6  →  Add rate limiting (single tenant, then multi-tenant)
Phase 7  →  Add failure handling, retries, and the reaper
Phase 8  →  Add observability (logging, metrics, tracing)
Phase 9  →  Load test and harden
Phase 10 →  Stretch goals (WFQ, circuit breakers, control plane)
```

---

## Phase 1 — The Synchronous Foundation

### Objective
Build a working job runner that accepts job definitions, executes them in order, and tracks their state — entirely in memory, entirely synchronous. No database. No queue. No async. Just a clean, working loop.

### System Scope
**What exists:**
- A `JobRunner` class with an in-memory job list
- A `Job` dataclass (id, type, payload, status, created_at)
- A small set of job handler functions (2–3 fake ones: `send_email`, `generate_report`, `resize_image`)
- A simple CLI or test script to submit and run jobs

**What is intentionally NOT here:**
- No HTTP API (yet)
- No database
- No concurrency
- No queue
- No retries

### Constraints Introduced
**Constraint:** All job state lives in a Python list in memory.

Why this matters: Forces you to think about what "state" means for a job. What fields does a job actually need? What does it mean for a job to "fail"? What happens to state when the process dies? You will feel this limitation acutely — that feeling is important.

### Implementation Requirements
- Define a `JobStatus` enum: `PENDING`, `RUNNING`, `SUCCESS`, `FAILED`
- Define a `Job` dataclass with: `id` (UUID), `type`, `payload` (dict), `status`, `created_at`, `started_at`, `completed_at`, `error_message`
- Write a `JobRunner.submit(job_type, payload) -> Job` method
- Write a `JobRunner.run_next() -> None` method that picks the first `PENDING` job, runs its handler, and updates status
- Write a `JobRunner.run_all() -> None` loop
- Handlers receive the job payload and either return normally (success) or raise an exception (failure)
- **DO NOT** use threads, asyncio, or any concurrency primitives yet

### Success Criteria
- You can submit 10 jobs and run them all sequentially
- A handler that raises an exception marks the job `FAILED` with the error message captured
- A handler that succeeds marks the job `SUCCESS` with `completed_at` set
- Job state is inspectable at any point (you can print all jobs and their statuses)
- No global variables — all state lives inside the `JobRunner` instance

### Expected Failures / Pain Points
- You will be tempted to make this complicated. Resist.
- The `Job` dataclass design will feel trivial — you will discover it was wrong in Phase 3 when Postgres forces you to reconsider every field
- You will not handle the case where `run_next()` is called with no pending jobs — handle it gracefully

### Concepts You Must Learn
- **Python dataclasses** — understand `field(default_factory=...)` and why you don't use mutable defaults
- **Enum in Python** — why `JobStatus.PENDING` is better than the string `"pending"`
- **UUID generation** — `uuid.uuid4()` and why UUIDs, not sequential integers, for distributed systems
- **Exception handling patterns** — the difference between catching `Exception` vs specific exceptions

### If You Get Stuck
- Search: "Python dataclass with default_factory"
- Search: "Python enum best practices"
- Search: "why use UUID instead of auto increment id"

### Reflection Questions
1. What happens to all your jobs if the Python process crashes after 5 of 10 jobs complete?
2. Why is `completed_at` a separate field from `started_at`? What does that gap tell you?
3. If a handler takes 30 seconds to run, what is the entire system doing during that time?
4. Your `run_all()` loop processes jobs in submission order. Is that always correct? What could go wrong?

---

## Phase 2 — Introduce Async Execution

### Objective
Convert the job runner to use `asyncio`. Understand *why* async matters for I/O-bound work, and experience the difference between concurrency and parallelism hands-on.

### System Scope
**What exists:**
- Everything from Phase 1, now async
- An `asyncio`-based runner loop
- Handlers are now `async def` functions
- A simulated I/O delay in each handler (`await asyncio.sleep(n)`)

**What is intentionally NOT here:**
- No real I/O yet (no DB, no network calls)
- No multiple workers
- No queue

### Constraints Introduced
**Constraint:** Handlers must be async. The runner must not block the event loop.

Why this matters: Every real backend job involves I/O — database writes, HTTP calls, file operations. Blocking the event loop while waiting for I/O wastes CPU and kills throughput. This is the foundational constraint of all modern Python backend systems.

### Implementation Requirements
- Convert all handler functions to `async def`
- Convert `JobRunner` methods to `async def`
- Use `asyncio.sleep()` in handlers to simulate I/O (e.g., 0.5–2 seconds)
- Implement `run_all()` as a coroutine that runs jobs **concurrently** using `asyncio.TaskGroup` (Python 3.11+)
- Add a **semaphore** to limit how many jobs run concurrently: `asyncio.Semaphore(max_concurrent=3)`
- Add a **timeout** per job using `asyncio.timeout(seconds=10)` — if a handler exceeds the budget, it should raise `TimeoutError` and be marked `FAILED`
- Add a simple `asyncio.run(runner.run_all())` entrypoint

**DO NOT** use `asyncio.gather()` — use `TaskGroup`. Understand why `TaskGroup` has better error propagation semantics.

### Success Criteria
- Submit 10 jobs. They run concurrently (not sequentially). The total time should be close to `max(handler_durations) / concurrency_slots`, not the sum of all durations.
- With `max_concurrent=3`, never more than 3 handlers run simultaneously. Add a counter to verify this.
- A handler that sleeps for 20 seconds is killed after 10 seconds by the timeout. Its job is marked `FAILED` with `"timeout"` in the error message.
- The runner does not crash when one job fails — the other jobs continue.

### Expected Failures / Pain Points
- You will accidentally write a blocking operation inside an async handler (e.g., `time.sleep()` instead of `asyncio.sleep()`). This will block the entire event loop. You will notice because all other jobs stall.
- `TaskGroup` cancellation semantics will confuse you — if one task raises an unhandled exception, `TaskGroup` cancels all others. Understand this behavior and decide if that's what you want.
- The semaphore must be acquired *inside* the task, not before creating it. Get this wrong and you'll serialize everything.

### Concepts You Must Learn
- **asyncio event loop** — single thread, cooperative multitasking. Draw this on paper.
- **coroutines vs threads** — coroutines yield control voluntarily at `await` points; threads are preempted by the OS
- **asyncio.TaskGroup** — structured concurrency, why it's better than raw `gather()`
- **asyncio.Semaphore** — what it is, what "acquiring" means, why you release it even on failure
- **asyncio.timeout()** — Python 3.11+ context manager, how it differs from `wait_for()`

### If You Get Stuck
- Search: "Python asyncio TaskGroup vs gather"
- Search: "asyncio Semaphore example"
- Search: "Python asyncio blocking event loop how to detect"
- Watch: "Python asyncio explained" by ArjanCodes or mCoding on YouTube

### Reflection Questions
1. You have 10 jobs and `max_concurrent=3`. Draw the execution timeline on paper. Which jobs run first? What determines the order?
2. What is the difference between concurrency and parallelism? Is `asyncio` giving you one or both?
3. If one of your handlers makes a `requests.get()` call (the synchronous HTTP library), what happens to your event loop? How would you fix it?
4. Why does `asyncio.timeout()` raise a `TimeoutError` that you must catch? What happens if you don't catch it?

---

## Phase 3 — Persistent State with Postgres

### Objective
Replace the in-memory job list with Postgres. Design a real job state machine. Experience the difference between "it works in memory" and "it works durably."

### System Scope
**What exists:**
- Phase 2 runner, now backed by Postgres
- A `jobs` table and a `job_events` table
- An `asyncpg` connection pool
- Status transitions enforced at the DB layer

**What is intentionally NOT here:**
- No queue yet (jobs still submitted and run in the same process)
- No multi-tenancy
- No rate limiting

### Constraints Introduced
**Constraint:** All job state must survive a process restart. If you kill the process mid-run, jobs in `RUNNING` state must be detectable and recoverable.

Why this matters: In-memory state is the biggest lie in backend systems. Production systems crash. The DB is your truth. Everything else is a cache.

### Implementation Requirements

**Schema** — implement these exact tables:
```sql
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','running','success','failed','dead')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    scheduled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    worker_id TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE job_events (
    id BIGSERIAL PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES jobs(id),
    event_type TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT,
    worker_id TEXT,
    metadata JSONB,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_jobs_status_scheduled ON jobs(status, scheduled_at);
CREATE INDEX idx_job_events_job_id ON job_events(job_id);
```

- Use `asyncpg` directly — not SQLAlchemy. Write raw SQL. Understand what you're doing.
- Create an `asyncpg.create_pool()` connection pool at startup
- Replace all in-memory state mutations with DB writes
- Write a `transition_status(job_id, old_status, new_status, worker_id)` function that uses an **optimistic lock**:
  ```sql
  UPDATE jobs SET status=$3, worker_id=$4, started_at=NOW()
  WHERE id=$1 AND status=$2
  RETURNING id
  ```
  If this returns no rows, someone else already transitioned this job. Handle that.
- Write every status transition as both an `UPDATE` to `jobs` AND an `INSERT` to `job_events`. Both in a single transaction.
- Use `TIMESTAMPTZ` everywhere. No `datetime.now()`. Use `datetime.now(timezone.utc)` if you need a Python datetime.

**For DB setup:** use Docker Compose with a Postgres container. Write a `schema.sql` file. Write a `bootstrap.py` script that creates the schema on first run.

### Success Criteria
- Kill the process after 3 of 10 jobs complete. Restart. The completed jobs stay `SUCCESS`. The remaining `PENDING` jobs resume.
- A job attempted while another transaction holds a lock on it does NOT duplicate-execute. Prove this with a test.
- The `job_events` table gives you a complete audit trail. For any job, you can reconstruct its full lifecycle.
- Run `EXPLAIN ANALYZE` on your worker polling query: `SELECT * FROM jobs WHERE status='pending' ORDER BY scheduled_at LIMIT 1`. Confirm it uses the index.

### Expected Failures / Pain Points
- `asyncpg` returns records, not dicts. You will try `row["field"]` and get confused. It works, but the API is different from what you expect.
- Your `transition_status` optimistic lock will fail silently the first time you write it. Add a log line when the `RETURNING` comes back empty.
- You will forget to commit transactions. asyncpg auto-begins but does not auto-commit. Understand `async with conn.transaction():`.
- Your `TIMESTAMPTZ` columns will confuse Python's timezone-naive `datetime` objects. This is intentional pain — learn it now.

### Concepts You Must Learn
- **Connection pooling** — why not one connection per request; what pool_min_size/pool_max_size mean
- **Optimistic locking** — check-and-swap at the DB layer, no explicit locks held
- **Pessimistic locking** — `SELECT FOR UPDATE SKIP LOCKED` — you'll need this in Phase 5
- **TIMESTAMPTZ vs TIMESTAMP** — always use `TIMESTAMPTZ`. Understand why.
- **JSONB in Postgres** — when to use it vs typed columns; indexing JSONB fields
- **Database transactions** — ACID properties, what "commit" actually means

### If You Get Stuck
- Search: "asyncpg Python tutorial connection pool"
- Search: "optimistic locking vs pessimistic locking explained"
- Search: "Postgres TIMESTAMPTZ vs TIMESTAMP difference"
- Search: "EXPLAIN ANALYZE Postgres how to read"

### Reflection Questions
1. You have a `job_events` table that is append-only. You never `UPDATE` or `DELETE` it. Why is this valuable? What can you do with it that you can't do with just the `jobs` table?
2. Your optimistic lock uses `WHERE status='pending'`. What happens if two workers call `transition_status` simultaneously for the same job? Walk through both execution paths exactly.
3. Why is `TIMESTAMPTZ` important in a distributed system? What goes wrong if you use timezone-naive timestamps and you have workers in different timezones?
4. What is the performance difference between polling `SELECT * FROM jobs WHERE status='pending'` with and without an index on `(status, scheduled_at)`? Use `EXPLAIN ANALYZE` to find out.

---

## Phase 4 — Decouple with a Redis Queue

### Objective
Separate job submission from job execution. A job is submitted via an HTTP API, written to Postgres, and a lightweight reference is pushed to Redis Streams. Workers read from the stream independently.

### System Scope
**What exists:**
- A FastAPI HTTP service for job submission (`POST /jobs`, `GET /jobs/{id}`)
- Postgres as the job store (from Phase 3)
- Redis Streams as the job queue
- A separate worker process that reads from the stream

**What is intentionally NOT here:**
- No multi-tenancy
- No rate limiting
- Still one worker

### Constraints Introduced
**Constraint:** The submission path and execution path are now in separate processes. They share only Postgres and Redis.

Why this matters: This is the decoupling that makes systems scalable. The API can accept 10,000 job submissions per second without caring if the worker is busy. This also introduces the first real distributed systems problem: what if the job is written to Postgres but the Redis push fails?

### Implementation Requirements
- Stand up FastAPI with `uvicorn`. Two endpoints:
  - `POST /jobs` — validates payload, writes to Postgres (`status=pending`), pushes `job_id` to Redis Stream, returns `{id, status}`
  - `GET /jobs/{id}` — reads job from Postgres, returns current state
- Use `redis.asyncio` client. Connect via `aioredis` or `redis-py` async.
- Use **Redis Streams** (`XADD`/`XREADGROUP`), not a Redis List. Understand why.
  - Create a consumer group: `XGROUP CREATE jobs:queue mygroup $ MKSTREAM`
  - Workers use `XREADGROUP GROUP mygroup worker-1 COUNT 5 BLOCK 2000 STREAMS jobs:queue >`
  - Acknowledge processed messages: `XACK jobs:queue mygroup message_id`
- The job payload stays in Postgres. Only the `job_id` goes in the stream.
- Worker is a standalone Python script, not a FastAPI endpoint. It runs its own `asyncio` loop.
- Handle the case where Redis `XADD` fails after Postgres write: the job sits in `PENDING` in Postgres forever. You'll fix this properly in Phase 7.

**Project structure at this point:**
```
job_engine/
  api/
    main.py          # FastAPI app
    routes.py
  worker/
    main.py          # Worker process
    handlers.py
  db/
    pool.py
    queries.py
  queue/
    redis_client.py
  models.py
  docker-compose.yml
```

### Success Criteria
- Submit a job via `curl`. The API returns instantly.
- The worker picks up the job and executes it.
- `GET /jobs/{id}` reflects the real-time status.
- Kill the worker mid-execution. Restart it. The job is **not re-processed** (because the `XACK` was never sent, the message becomes a "pending entry" in the consumer group — the worker should reclaim it on restart using `XAUTOCLAIM`).
- Submit 100 jobs rapidly. All 100 appear in Postgres. All 100 are eventually processed. None are lost or duplicated.

### Expected Failures / Pain Points
- You will forget to `XACK` and wonder why jobs keep re-running. This is a crucial learning moment — do not fix it immediately, understand why it's happening first.
- Redis Stream consumer group semantics will be confusing. Read the Redis Streams documentation carefully. Not a tutorial — the actual docs.
- The worker's startup sequence matters. If the consumer group doesn't exist yet, `XREADGROUP` will throw. Handle this in the worker's initialization.
- You will hit race conditions between Postgres write and Redis push. Log when this happens. In Phase 7, you'll fix it properly.

### Concepts You Must Learn
- **Redis Streams vs Redis Lists** — at-least-once delivery, consumer groups, message acknowledgment
- **At-least-once vs exactly-once delivery** — why exactly-once is nearly impossible; why at-least-once + idempotency is the real solution
- **Consumer groups in Redis** — what a "pending entry list" (PEL) is and why it exists
- **Message acknowledgment** — why unacknowledged messages are not lost
- **XAUTOCLAIM** — reclaiming messages from dead consumers

### If You Get Stuck
- Search: "Redis Streams tutorial consumer groups"
- Search: "Redis Streams vs Redis List queue"
- Read: redis.io/docs/data-types/streams/ (the official docs, not a blog post)
- Search: "XAUTOCLAIM Redis example Python"

### Reflection Questions
1. You push `job_id` to Redis, not the full job payload. Why? What is wrong with putting the full payload in the stream?
2. What is the difference between `XREAD` and `XREADGROUP`? Why does it matter for a multi-worker setup?
3. A message is in the Redis consumer group's "pending entry list" (PEL). What does that mean exactly? Under what condition does it get removed from the PEL?
4. The job write to Postgres succeeds, but the Redis `XADD` fails due to a network blip. The job now exists in Postgres but is not in the queue. How would you detect this? How would you recover it?

---

## Phase 5 — Multiple Workers and the Concurrency Problem

### Objective
Run 3+ workers simultaneously. Watch jobs get duplicate-executed. Fix it. Understand why distributed concurrency is the hardest part of backend systems.

### System Scope
**What exists:**
- Everything from Phase 4
- Multiple worker processes running simultaneously (use Docker Compose `scale`)
- Each worker has a unique `worker_id` (hostname + PID)

**What is intentionally NOT here:**
- No rate limiting yet
- No multi-tenancy yet

### Constraints Introduced
**Constraint:** Multiple workers compete for the same jobs. At most one worker must execute each job.

Why this matters: This is the core distributed systems problem. In a single process, mutual exclusion is easy — one goroutine, one lock. In a distributed system, there is no shared memory. Correctness requires coordination across processes, and that coordination can fail.

### Implementation Requirements
- Start 3 workers simultaneously using Docker Compose `deploy: replicas: 3`
- Each worker must have a unique `worker_id`: `f"{socket.gethostname()}-{os.getpid()}"`
- Redis consumer groups already give you per-message exclusivity — one message goes to one consumer. But verify this: add a counter to Postgres and assert it's only incremented once per job.
- Add the optimistic lock you wrote in Phase 3 to the `transition_status` call inside the worker. A worker that loses the race (gets no rows back from the `UPDATE ... RETURNING`) must:
  1. Log that it lost the race
  2. `XACK` the message anyway (it doesn't want to reprocess it)
  3. Move to the next job
- Add a test: submit 50 jobs, run 3 workers, assert every job has `attempt_count = 1` in Postgres (not 2 or 3)

**New failure mode to introduce intentionally:**
- Pause one worker (`docker pause <container>`) mid-processing. The messages it was processing stay in the PEL indefinitely.
- After 30 seconds, have another worker call `XAUTOCLAIM` to reclaim those stuck messages.
- Observe: the reclaimed jobs might now run a second time if `XACK` was never sent. This is the at-least-once problem. Your optimistic lock in Postgres is what saves you.

### Success Criteria
- Submit 100 jobs. Run 3 workers simultaneously. Every job reaches `SUCCESS` or `FAILED` exactly once. Zero jobs have `attempt_count > 1` (in the happy path).
- Pause a worker for 60 seconds mid-run. The remaining workers eventually reclaim the stuck jobs via `XAUTOCLAIM`. The paused worker's jobs complete (possibly on different workers).
- No panics, no crashes, no deadlocks. Workers handle lost-race gracefully.

### Expected Failures / Pain Points
- You will see duplicate execution before you add the optimistic lock. Log and study this — it's the most important bug in distributed systems.
- The `XAUTOCLAIM` timing is tricky. If you set the visibility timeout too short, you'll get false positives (reclaiming a job that's still running).
- Workers logging "lost the race" is not an error — it's expected. Make sure your logging level reflects this.

### Concepts You Must Learn
- **Distributed mutual exclusion** — why you can't use a Python `threading.Lock()` across processes
- **Optimistic concurrency control** — compare-and-swap at the DB layer
- **Visibility timeout** — the window after which an unacknowledged message is considered abandoned
- **Idempotency** — designing operations so running them twice produces the same result as running once
- **At-least-once delivery** — why it's the default and how to make your system safe under it

### If You Get Stuck
- Search: "distributed locking Redis vs database optimistic locking"
- Search: "idempotency backend systems explained"
- Search: "XAUTOCLAIM Redis reclaim dead consumer messages"

### Reflection Questions
1. Redis consumer groups give you per-message routing to one consumer. Your Postgres optimistic lock also prevents double execution. You have two layers of protection. Is that redundant, or is each protecting against a different failure mode? Explain both.
2. What is the difference between idempotency and exactly-once delivery? Why is idempotency more achievable?
3. You set your `XAUTOCLAIM` visibility timeout to 30 seconds. A handler legitimately takes 45 seconds. What happens? How would you fix this?
4. Your optimistic lock is: `UPDATE jobs SET status='running' WHERE id=$1 AND status='pending'`. Worker A and Worker B both see the job as `pending` and both fire this query simultaneously. Walk through what Postgres does. Which worker wins? What does the other one see?

---

## Phase 6 — Rate Limiting (Single Tenant First)

### Objective
Implement a token bucket rate limiter in Redis using a Lua script. Enforce a per-tenant execution rate. This is the centerpiece of the whole system — build it carefully.

### System Scope
**What exists:**
- Everything from Phase 5
- A `tenants` table in Postgres
- A token bucket per tenant stored in Redis
- Rate limit check happens before job execution in the worker

**What is intentionally NOT here:**
- Start with a SINGLE tenant. Do not implement multi-tenancy yet.
- No priority queues yet

### Constraints Introduced
**Constraint:** A tenant can execute at most N jobs per second, with a burst capacity of B.

Why this matters: Without rate limiting, one misbehaving tenant can consume all worker capacity and starve everyone else. This is a real problem at every multi-tenant SaaS company.

### Implementation Requirements

**Token Bucket Algorithm — understand this before you implement it:**
- A bucket has a max capacity B (burst capacity)
- Tokens refill at rate R per second
- Each job execution consumes 1 token
- If the bucket is empty, the job cannot execute yet

**Lua script for atomic check-and-decrement** — you must write this yourself:
```lua
-- Keys: [bucket_key]
-- Args: [max_tokens, refill_rate, now_timestamp, tokens_requested]
-- Returns: [allowed (0/1), remaining_tokens]

local key = KEYS[1]
local max_tokens = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])

local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(bucket[1]) or max_tokens
local last_refill = tonumber(bucket[2]) or now

-- Calculate tokens to add based on elapsed time
local elapsed = math.max(0, now - last_refill)
local new_tokens = math.min(max_tokens, tokens + (elapsed * refill_rate))

if new_tokens >= requested then
    -- Allow: decrement tokens
    redis.call('HMSET', key, 'tokens', new_tokens - requested, 'last_refill', now)
    redis.call('EXPIRE', key, 3600)
    return {1, new_tokens - requested}
else
    -- Deny: update refill timestamp but don't change tokens
    redis.call('HMSET', key, 'tokens', new_tokens, 'last_refill', now)
    redis.call('EXPIRE', key, 3600)
    return {0, new_tokens}
end
```

- Register this script with `redis.register_script()` — do not `EVAL` it inline on every call
- In the worker, before executing a job, call the Lua script with the tenant's rate limit config
- If the script returns `allowed=0`: do NOT `XACK` the message. Put the job back in a "delayed" state and retry after a backoff.
- Add a `tenants` table to Postgres:
  ```sql
  CREATE TABLE tenants (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      name TEXT NOT NULL UNIQUE,
      rate_limit_rps FLOAT NOT NULL DEFAULT 10,
      burst_capacity INTEGER NOT NULL DEFAULT 20
  );
  ```
- Cache tenant config in Redis with a 60-second TTL. Invalidate on update.

**Backoff strategy when rate-limited:**
- Do not busy-loop. Calculate `retry_after = 1.0 / rate_limit_rps` and `asyncio.sleep(retry_after + jitter)`
- `jitter = random.uniform(0, 0.1)` — prevents thundering herd

### Success Criteria
- Set tenant rate limit to 5 RPS. Submit 100 jobs rapidly. Confirm jobs execute at roughly 5/sec (measure via `completed_at` timestamps in Postgres).
- With burst capacity of 20, the first 20 jobs execute immediately even at 5 RPS. Prove this.
- Set rate limit to 0.5 RPS (one job every 2 seconds). Submit 10 jobs. They execute with ~2 second gaps.
- The Lua script call is **atomic** — prove this by describing (not necessarily testing) what happens if two workers call it simultaneously for the same tenant.

### Expected Failures / Pain Points
- You will get the `last_refill` timestamp logic wrong the first time. Off-by-one in milliseconds vs seconds will break everything. Use a consistent unit (seconds as float: `time.time()`).
- Redis `HMGET` returns strings, not numbers. Your Lua script must `tonumber()` everything. Forgetting this gives silent nil behavior.
- The `EXPIRE` call is important — without it, buckets for inactive tenants fill your Redis memory forever.
- Backoff without jitter causes thundering herd: all workers wake up at the same millisecond and hammer the rate limiter together. Add jitter.

### Concepts You Must Learn
- **Token bucket algorithm** — vs leaky bucket, vs sliding window. Know all three; implement token bucket.
- **Lua scripting in Redis** — why Lua guarantees atomicity (Redis is single-threaded; Lua runs without interruption)
- **Redis EVAL vs registered scripts** — SHA-based script registration, why it's more efficient
- **Thundering herd** — what it is, why it happens, how jitter fixes it
- **Backpressure** — the principle of slowing down producers when consumers can't keep up

### If You Get Stuck
- Search: "token bucket algorithm explained"
- Search: "Redis Lua script atomic operations"
- Search: "redis register_script Python redis-py"
- Search: "thundering herd problem jitter solution"

### Reflection Questions
1. Your Lua script runs atomically. What does "atomically" mean in the context of Redis? Why can't you achieve the same thing with a Python `if` statement that checks and then decrements?
2. You cache tenant config for 60 seconds. An operator reduces a tenant's rate limit from 100 RPS to 5 RPS due to abuse. How long until the new limit takes effect? Is this acceptable?
3. The token bucket has burst capacity B and refill rate R. A tenant is idle for 10 minutes. Their bucket is now full. They then submit 1000 jobs instantly. What happens? Is this the behavior you want?
4. What is the difference between rate limiting at the API layer (limit job submissions) vs rate limiting at the worker layer (limit job executions)? Which is this system doing, and why?

---

## Phase 7 — Multi-Tenancy, Priority Queues, and Failure Handling

### Objective
Extend to multiple tenants with different rate limits. Add priority queues. Implement retry logic and the reaper that recovers orphaned jobs.

### System Scope
**What exists:**
- Everything from Phase 6
- Multiple tenants with different rate limits
- Three priority queues: `jobs:high`, `jobs:normal`, `jobs:low`
- Retry logic with exponential backoff
- A reaper coroutine that runs alongside the worker

**What is intentionally NOT here:**
- No circuit breakers yet (Phase 10)
- No observability yet (Phase 8)

### Constraints Introduced
**Constraint 1:** Jobs must be associated with a tenant. Rate limits are enforced per-tenant.
**Constraint 2:** High-priority jobs must not be starved by low-priority volume.
**Constraint 3:** Jobs that fail must be retried up to `max_attempts`. After that, they are `DEAD`.
**Constraint 4:** Workers that crash leave jobs stuck in `RUNNING`. These must be recovered.

### Implementation Requirements

**Multi-tenancy:**
- Every job now has a `tenant_id`
- The token bucket key becomes `rate_limit:{tenant_id}`
- Workers read tenant config from cache (60s TTL, populated from Postgres)
- Add an idempotency key to jobs:
  ```sql
  ALTER TABLE jobs ADD COLUMN idempotency_key TEXT;
  CREATE UNIQUE INDEX idx_jobs_idempotency ON jobs(tenant_id, idempotency_key)
      WHERE idempotency_key IS NOT NULL;
  ```
- In `POST /jobs`, if `idempotency_key` is provided and already exists for this tenant, return the existing job (with HTTP 200, not 409).

**Priority Queues:**
- Three Redis Streams: `jobs:high`, `jobs:normal`, `jobs:low`
- Worker polls with a **weighted strategy**: for every 5 polls of `jobs:high`, do 3 from `jobs:normal`, 1 from `jobs:low`
- Implement this as a stateful counter in the worker loop

**Retry Logic:**
- When a job fails (handler raises), increment `attempt_count`
- If `attempt_count < max_attempts`: re-queue with a delay using `scheduled_at = NOW() + exponential_backoff`
  - `backoff = min(2 ** attempt_count * base_delay, max_delay)`
  - Add jitter: `backoff + random.uniform(0, backoff * 0.1)`
- If `attempt_count >= max_attempts`: mark status `DEAD`. Do not retry.
- Write all of this as a status transition + job_events entry

**The Reaper:**
- A coroutine that runs in the worker process alongside the main worker loop
- Every 30 seconds, runs this query:
  ```sql
  SELECT id, worker_id FROM jobs
  WHERE status = 'running'
  AND started_at < NOW() - INTERVAL '2 minutes'
  ```
- For each result: transition status back to `PENDING`, increment `attempt_count`, re-add to Redis Stream, insert a `job_events` record with `event_type='reaped'`
- The reaper does NOT care which worker was running the job. It only cares about the timestamp.

### Success Criteria
- Submit identical jobs twice with the same `idempotency_key`. Only one job is created. The second request returns the existing job.
- Submit 100 low-priority jobs and 10 high-priority jobs simultaneously. High-priority jobs complete first. Prove this by comparing `completed_at` timestamps.
- A handler that always fails reaches `DEAD` after `max_attempts`. Confirm `attempt_count = max_attempts` in Postgres.
- Kill a worker (`kill -9`) after it has been running a job for 10 seconds. Wait 2 minutes. The reaper picks up the orphaned job and re-queues it. The job completes on another worker.

### Expected Failures / Pain Points
- The weighted poll strategy is stateful — if a worker restarts, the counter resets. This is acceptable. Understanding why it's acceptable (it's not a correctness issue, only a fairness issue) is important.
- Exponential backoff with delayed scheduling means jobs sit in Postgres with `status='pending'` and a future `scheduled_at`. Your worker polling query must filter by `scheduled_at <= NOW()`.
- The reaper's 2-minute timeout must be longer than your job handler timeout. If handlers timeout at 60 seconds and the reaper reclaims after 90 seconds, you have a race. Design the timeouts deliberately.
- Multiple reaper instances (one per worker process) may reclaim the same job simultaneously. Your optimistic lock in `transition_status` handles this — make sure the reaper uses it.

### Concepts You Must Learn
- **Idempotency keys** — the standard pattern for deduplicating distributed requests
- **Dead letter queue** — where jobs go when all retries are exhausted
- **Exponential backoff with jitter** — the correct retry strategy for distributed systems
- **Orphan detection** — using heartbeats or timestamps to detect dead workers
- **Weighted fair queuing** — ensuring high-priority work doesn't completely starve low-priority work

### If You Get Stuck
- Search: "idempotency key design pattern API"
- Search: "exponential backoff with jitter AWS blog"
- Search: "dead letter queue pattern explained"
- Search: "orphaned job detection background worker"

### Reflection Questions
1. Your reaper reclaims a job after 2 minutes. The original worker was not dead — it was just very slow (a handler taking 2.5 minutes). Now two workers are running the same job. What saves you from corruption?
2. You implement exponential backoff but forget to add jitter. You have 10 workers, and a downstream service fails. All 10 workers fail their jobs at the same second. They all backoff for exactly 4 seconds and retry at the exact same time. What happens?
3. A job is in `DEAD` status. Is it truly dead, or can an operator resurrect it? How would you build that capability? What fields and transitions would you need?
4. Your priority queue system ensures high-priority jobs run first, but what happens to low-priority jobs if there is a constant stream of high-priority jobs? Is this starvation? How would you prevent it?

---

## Phase 8 — Observability: Logging, Metrics, and Tracing

### Objective
Instrument the entire system so you can understand what is happening without attaching a debugger. This is not optional polish — it is a core engineering requirement.

### System Scope
**What exists:**
- Full system from Phase 7
- Structured JSON logging via `structlog`
- Prometheus metrics exposed on `/metrics`
- OpenTelemetry distributed tracing with Jaeger
- Grafana dashboards

**What is intentionally NOT here:**
- No alerting rules yet (that's ops, not this project)

### Constraints Introduced
**Constraint:** You must be able to answer these questions without a debugger and without `print()`:
1. Which tenant is submitting the most jobs right now?
2. What is the P99 job execution time for each job type?
3. A job failed 3 hours ago — what happened, step by step?
4. Is the rate limiter working? How many rejections per tenant per minute?

### Implementation Requirements

**Structured Logging with `structlog`:**
- Every log line must be JSON in production, human-readable in development
- Every log line in the worker must include: `job_id`, `tenant_id`, `worker_id`, `attempt_count`
- Configure `structlog` with a context var processor so you set these once per job and they appear in every log line automatically:
  ```python
  import structlog
  from contextvars import ContextVar
  
  job_context: ContextVar[dict] = ContextVar('job_context', default={})
  ```
- Log levels matter: `DEBUG` for internal state, `INFO` for state transitions, `WARNING` for recoverable errors, `ERROR` for unrecoverable failures, `CRITICAL` for system-level problems (Redis down, Postgres unreachable)
- Never log raw exception tracebacks without context. Always add `exc_info=True` to the log call so it's captured but attached to a meaningful log line.

**Prometheus Metrics:**
- Add `prometheus-client` library
- Expose `/metrics` endpoint on the API
- Expose a separate metrics server on the worker (port 9090)
- Implement these specific metrics:
  ```python
  jobs_submitted_total = Counter('jobs_submitted_total', 'Total jobs submitted', ['tenant_id', 'priority'])
  jobs_completed_total = Counter('jobs_completed_total', 'Total jobs completed', ['tenant_id', 'job_type', 'status'])
  job_duration_seconds = Histogram('job_duration_seconds', 'Handler execution time', ['job_type'],
                                    buckets=[.01, .05, .1, .25, .5, 1, 2.5, 5, 10, 30])
  rate_limit_rejections_total = Counter('rate_limit_rejections_total', 'Rate limit hits', ['tenant_id'])
  worker_active_jobs = Gauge('worker_active_jobs', 'Currently executing jobs', ['worker_id'])
  queue_depth = Gauge('queue_depth', 'Jobs in queue', ['priority'])
  job_attempts_histogram = Histogram('job_attempt_count', 'Attempts per job', buckets=[1, 2, 3, 4, 5])
  ```
- Update metrics at the right places: `jobs_submitted_total` increments at submission, `worker_active_jobs` increments at start and decrements at completion (even on error — use try/finally).

**Distributed Tracing with OpenTelemetry:**
- Install `opentelemetry-sdk`, `opentelemetry-exporter-jaeger`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-asyncpg`
- A trace must span the entire job lifecycle: HTTP submission → queue → worker pickup → handler execution
- Propagate trace context: when a job is submitted, store the trace ID in the `jobs` table (`trace_id TEXT` column)
- In the worker, start a new span as a child of the submission span by reconstructing the context from the stored trace ID
- This means: given a `job_id` in Postgres, you can find the trace in Jaeger. Given a trace in Jaeger, you can find the job in Postgres.

**Grafana Dashboard — you must build this:**
- Run Prometheus + Grafana in Docker Compose
- Build a dashboard with these panels:
  - Jobs submitted/completed per second (by tenant)
  - Job success/failure rate over time
  - P50/P95/P99 job duration by job type
  - Rate limit rejection rate by tenant
  - Active jobs per worker
  - Queue depth over time

### Success Criteria
- Submit 1000 jobs from 3 tenants over 5 minutes. Your Grafana dashboard shows all metrics updating in real time.
- Find a specific failed job in Postgres. Use its `trace_id` to find the full trace in Jaeger. The trace shows every step from HTTP submission to failure, with timing.
- Every log line from the worker includes `job_id`, `tenant_id`, and `worker_id`. Verify with `grep` or `jq` on the log output.
- `worker_active_jobs` gauge never goes negative. Even if a handler crashes, the `try/finally` ensures it decrements.

### Expected Failures / Pain Points
- OpenTelemetry setup is verbose and its Python documentation is inconsistent. Budget extra time.
- The trace context propagation across process boundaries (API → worker) is the hardest part. The `trace_id` stored in Postgres is the bridge. You have to manually reconstruct the parent span context.
- Prometheus histograms seem simple until you realize your bucket boundaries are wrong and your P99 is being reported as the last bucket's ceiling. Choose buckets based on expected durations.
- `structlog` configuration order matters. If you configure processors in the wrong order, JSON output breaks.

### Concepts You Must Learn
- **Structured logging** — why JSON logs beat string logs for machines
- **Prometheus data model** — counters, gauges, histograms, summaries. Know the difference.
- **Histogram buckets** — why you must define them upfront, how to choose them
- **Distributed tracing** — spans, traces, trace context propagation
- **The three pillars of observability** — logs, metrics, traces. What each answers that the others can't.

### If You Get Stuck
- Search: "structlog Python production configuration JSON"
- Search: "prometheus-client Python histogram example"
- Search: "OpenTelemetry Python manual instrumentation"
- Search: "OpenTelemetry trace context propagation across services"
- Read: opentelemetry.io/docs/languages/python/

### Reflection Questions
1. You have logs, metrics, and traces. A job failed. Which do you look at first, and why? Walk through your actual debugging workflow.
2. Your `job_duration_seconds` histogram has buckets at [0.1, 0.5, 1, 5, 10]. A handler takes 0.3 seconds. Which bucket does it land in? What does the P95 calculation actually do with bucket data?
3. Why is a Gauge different from a Counter? What goes wrong if you use a Counter for `worker_active_jobs`?
4. The trace context stored in Postgres is just a string. How does the worker reconstruct a proper OpenTelemetry parent context from it? What format is the trace ID in?

---

## Phase 9 — Load Testing and Production Hardening

### Objective
Break the system under controlled load. Identify bottlenecks. Fix them. Produce evidence that the system works correctly at scale.

### System Scope
**What exists:**
- Full system from Phase 8
- Locust load test scenarios
- Connection pool tuning
- Graceful shutdown

**What is intentionally NOT here:**
- Real production infra (Kubernetes, cloud) — out of scope for this project

### Constraints Introduced
**Constraint:** The system must handle 100 concurrent job submissions from 5 tenants with different rate limits, without data loss, without duplicate execution, and with observable behavior throughout.

### Implementation Requirements

**Locust Load Tests — write these specific scenarios:**

Scenario 1: Steady state
- 10 users, each submitting 1 job/second for 5 minutes
- Assert: all jobs eventually complete, no duplicates

Scenario 2: Burst traffic
- 100 users submit jobs simultaneously
- Assert: the rate limiter triggers for high-volume tenants; low-volume tenants are not impacted

Scenario 3: Worker failure under load
- Start 3 workers. Kill one after 30 seconds. Kill another after 60 seconds.
- Assert: all jobs eventually complete on the remaining workers (reaper and `XAUTOCLAIM` kick in)

Scenario 4: Queue saturation
- Submit faster than workers can process for 60 seconds, then stop
- Assert: queue depth increases, then drains; no jobs are lost

**Graceful Shutdown:**
- Handle `SIGTERM` and `SIGINT` in the worker
- On shutdown signal: stop accepting new jobs, wait for in-flight jobs to complete (or until a 30-second deadline), then exit
- Implement using `asyncio.Event()` for the shutdown signal and `asyncio.wait_for()` with a timeout on the in-flight tasks

**Connection Pool Tuning:**
- Run load tests with pool sizes of 5, 10, and 20
- Measure: P99 query latency, connection wait time, pool exhaustion errors
- Set `pool_max_size` to the value where adding more connections stops improving latency

**The Chaos Tests — do these manually:**
1. Kill Redis. Workers should fail closed (stop processing) and emit `CRITICAL` log lines. The API should return 503 on new submissions.
2. Kill Postgres. Workers should fail closed. The API should return 503.
3. Restart both. The system should recover without operator intervention. All in-flight jobs should either complete or be reaped.

### Success Criteria
- Load test Scenario 1 completes with 0 duplicate executions (verified via Postgres `attempt_count`).
- Load test Scenario 3 completes with 100% of jobs eventually reaching `SUCCESS` or `FAILED`.
- Graceful shutdown: kill a worker with `SIGTERM`. It finishes its current job and exits. No job is stuck in `RUNNING`.
- Redis kill + restart: system recovers within 60 seconds. Workers resume processing. Log the exact recovery sequence.
- Your Grafana dashboard shows queue depth rising during burst and falling during drain. Screenshot this and put it in your README.

### Expected Failures / Pain Points
- Locust user count and spawn rate interact in non-obvious ways. Read the Locust docs on task weights.
- Connection pool exhaustion is silent — requests just hang waiting for a connection. Add `command_timeout` to asyncpg to surface this.
- Graceful shutdown with `asyncio` requires careful task tracking. Keep a `Set[asyncio.Task]` of in-flight tasks in the worker and await their completion on shutdown.
- Your Redis kill test will reveal that you didn't handle `redis.exceptions.ConnectionError` everywhere. Fix all of them.

### Concepts You Must Learn
- **Connection pool exhaustion** — what happens when all pool connections are in use
- **Graceful shutdown** — SIGTERM vs SIGKILL, drain vs kill
- **Load testing methodology** — throughput vs latency, Amdahl's Law for scaling
- **Chaos engineering** — controlled failure injection to build confidence in recovery paths
- **Backpressure** — what happens when consumers can't keep up with producers; how to expose that pressure upward

### If You Get Stuck
- Search: "Python asyncio graceful shutdown SIGTERM"
- Search: "asyncpg connection pool exhaustion timeout"
- Search: "locust load test Python tutorial"
- Search: "chaos engineering principles Netflix"

### Reflection Questions
1. You ran the burst traffic test and the system slowed down but didn't crash. What is the bottleneck: CPU, DB connections, Redis throughput, or network? How would you determine which?
2. Graceful shutdown waits up to 30 seconds for in-flight jobs. What happens to a job that takes 45 seconds? Is the behavior correct? How would you change it?
3. After killing and restarting Redis, your workers start recovering. What is the sequence of events? Walk through exactly what each component does: API, worker, reaper, Redis consumer group, Postgres.
4. You run the load test and find that P99 latency is 10x the P50. What does this tell you? What are the likely causes?

---

## Phase 10 — Stretch Goals (Senior-Level Signal)

### Stretch Goal A: Weighted Fair Queuing

**Objective:** Replace the simple token bucket per tenant with Weighted Fair Queuing (WFQ). Each tenant has a weight. The worker always picks the job with the smallest "virtual finish time," which is computed from the tenant's weight and the last time they were served.

This is how Linux's Completely Fair Scheduler works. Implementing it proves you understand scheduling theory.

**What to implement:**
- Each tenant has a `weight` (integer, default 1)
- Each tenant has a `virtual_clock` stored in Redis (float, initialized to `current_time`)
- When a job is dequeued, compute `virtual_finish_time = tenant.virtual_clock + (1.0 / tenant.weight)`
- The worker always picks the pending job with the smallest `virtual_finish_time`
- After executing a job, update `tenant.virtual_clock = virtual_finish_time`

**Research:** "Weighted Fair Queuing algorithm" and "Linux Completely Fair Scheduler."

---

### Stretch Goal B: Per-Job-Type Circuit Breaker

**Objective:** If a job handler starts failing consistently, stop executing that job type temporarily. This prevents a broken downstream dependency from consuming all worker capacity.

**What to implement:**
- Each job type has a circuit breaker with three states: `CLOSED` (normal), `OPEN` (failing, reject all), `HALF_OPEN` (testing recovery)
- State stored in Redis with a TTL
- If failure rate exceeds 50% over a 60-second sliding window → `OPEN`
- After 30 seconds in `OPEN` → `HALF_OPEN` (allow one job through)
- If that job succeeds → `CLOSED`. If it fails → back to `OPEN`.
- Expose circuit state in Prometheus metrics and API (`GET /circuit-breakers`)

**Research:** "Circuit breaker pattern Martin Fowler" and "Resilience4j circuit breaker states."

---

### Stretch Goal C: Tenant Control Plane API

**Objective:** Add an authenticated control plane API that tenants can use to inspect their own job history, see their current token bucket state, and adjust job priorities.

**What to implement:**
- API key authentication (store hashed keys in Postgres; never store plaintext)
- Endpoints:
  - `GET /me/jobs` — paginated, filterable by status and date range
  - `GET /me/rate-limit` — current token bucket state (tokens remaining, last refill)
  - `POST /me/jobs/{id}/cancel` — cancel a pending job (not a running one)
- Row-level security: tenants can only see their own data. Enforce in SQL (`WHERE tenant_id = $current_tenant`), not just in application code.
- Rate limit the control plane API itself (separate limiter from the job execution limiter)

**Research:** "API key authentication patterns" and "Postgres row-level security."

---

## Phase Completion Checklist

```
PHASE 1 — Synchronous Foundation
[ ] Job dataclass with all required fields
[ ] JobRunner with submit() and run_all()
[ ] Status transitions work correctly
[ ] Failed handlers mark jobs FAILED with error captured
[ ] No global state

PHASE 2 — Async Execution
[ ] All handlers are async def
[ ] asyncio.TaskGroup used for concurrent execution
[ ] Semaphore limits concurrent jobs
[ ] asyncio.timeout() kills slow handlers
[ ] No blocking calls in async context

PHASE 3 — Postgres Persistence
[ ] jobs and job_events tables created
[ ] asyncpg connection pool initialized
[ ] Optimistic lock on status transitions
[ ] Every transition writes to job_events
[ ] TIMESTAMPTZ everywhere
[ ] Indexes created and verified with EXPLAIN ANALYZE

PHASE 4 — Redis Queue
[ ] FastAPI submission endpoint
[ ] Redis Streams with consumer groups
[ ] Worker is a separate process
[ ] XAUTOCLAIM handles dead consumer recovery
[ ] Job payload in Postgres, only job_id in stream

PHASE 5 — Multiple Workers
[ ] 3 workers run simultaneously without duplicates
[ ] Each worker has a unique worker_id
[ ] Optimistic lock verified under concurrent workers
[ ] Worker pause + XAUTOCLAIM recovery tested

PHASE 6 — Rate Limiting
[ ] Token bucket Lua script written and tested
[ ] Script registered, not EVAL'd inline
[ ] Tenant config cached with TTL
[ ] Backoff with jitter when rate-limited
[ ] Rate limit verified at correct RPS

PHASE 7 — Multi-Tenancy and Failures
[ ] Idempotency key deduplication working
[ ] Three priority queues with weighted polling
[ ] Retry with exponential backoff + jitter
[ ] DEAD status after max_attempts
[ ] Reaper recovers orphaned RUNNING jobs
[ ] Reaper uses optimistic lock

PHASE 8 — Observability
[ ] structlog configured, all logs are JSON in prod
[ ] Every worker log includes job_id, tenant_id, worker_id
[ ] All 7 Prometheus metrics implemented
[ ] Grafana dashboard with all required panels
[ ] OpenTelemetry tracing spans full job lifecycle
[ ] trace_id stored in Postgres, retrievable in Jaeger

PHASE 9 — Load Testing
[ ] All 4 Locust scenarios written and passing
[ ] Graceful shutdown on SIGTERM tested
[ ] Connection pool size tuned with evidence
[ ] Redis kill + restart recovery tested
[ ] Postgres kill + restart recovery tested
[ ] Load test results (Grafana screenshots) in README

PHASE 10 — Stretch Goals (Optional)
[ ] Weighted Fair Queuing implemented
[ ] Circuit breaker per job type
[ ] Tenant control plane API with row-level security
```

---

## Final Validation: What a Correctly Built System Looks Like

### Correctness Tests
Run these to verify your system is actually correct:

1. **Duplicate execution test:** Submit 1 job. Kill a worker after it picks up the job but before it completes. Wait for the reaper. Assert the job runs exactly once more and completes. Assert `attempt_count = 2`. Assert `job_events` shows `reaped` event.

2. **Rate limit accuracy test:** Set a tenant to 10 RPS. Submit 1000 jobs. Measure `completed_at` timestamps in Postgres. Assert the average throughput is within 10% of 10/second after the burst capacity is exhausted.

3. **Idempotency test:** Submit 50 identical jobs (same idempotency key) in a tight loop. Assert exactly 1 job exists in Postgres. Assert all 50 API calls return 200 with the same job ID.

4. **Priority ordering test:** Submit 200 low-priority jobs. Then submit 20 high-priority jobs. With workers at capacity, assert high-priority jobs complete before more than 10 low-priority jobs complete.

5. **Graceful shutdown test:** Start a worker with 5 jobs in-flight. Send SIGTERM. Assert all 5 jobs complete successfully. Assert the worker exits within `timeout + 5 seconds`. Assert no jobs stuck in `RUNNING`.

6. **Zero data loss test:** Submit 500 jobs. Randomly kill and restart workers throughout execution. Assert all 500 jobs eventually reach `SUCCESS` or `DEAD`. Zero jobs stuck in `RUNNING` or `PENDING` after execution completes.

### The "Senior Engineer Would Approve" README Checklist
Your README must contain:
- [ ] Architecture diagram with components and data flow
- [ ] "Design decisions" section explaining 3+ tradeoffs (e.g., "why Redis Streams over RabbitMQ")
- [ ] "Running locally" instructions that work from a clean clone in under 5 minutes
- [ ] Load test results with Grafana screenshots
- [ ] "Known limitations" section (every real system has them; listing them shows maturity)
- [ ] Brief explanation of what the reaper does and why it exists
- [ ] Explanation of why the Lua script must be atomic

---

## Final Note to Yourself

Every phase will feel uncomfortable. That discomfort is the actual learning.

When you hit a bug you cannot explain — a job that double-executes, a race condition you cannot reproduce consistently, a metric that doesn't match your expectation — **do not immediately search for the fix.** Sit with the problem. Form a hypothesis. Test the hypothesis. Then search.

The engineers who become good at distributed systems are the ones who build mental models of what's happening in the system at every moment. The code is just the expression of that model.

When you finish Phase 5 and you understand exactly why two workers could double-execute a job and exactly what prevents it, you will have learned something that no tutorial can teach you.

Build it. Break it. Fix it. Explain it.
