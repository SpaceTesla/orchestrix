# Dev Notes

A running log of discoveries, mistakes, and "aha" moments phase by phase.

> Write here while things are fresh. Future-you will thank you. These notes are also useful to review before jumping to the next phase — they reveal which concepts you actually internalized vs. just got to work.

---

## Format

Each entry:

```
### [Phase N] Short title
Date: YYYY-MM-DD
What happened / what I learned / what tripped me up
```

---

## Phase 1 — Synchronous Foundation

*(Start adding notes here once you begin Phase 1)*

### Questions to answer before you write a line of code

Before starting Phase 1, try to answer these without looking anything up:

1. What fields does a `Job` actually need? What does a job need to *remember* about itself?
2. What happens if `run_next()` is called and there are no pending jobs? How should it behave?
3. Why use `uuid.uuid4()` for job IDs instead of an auto-incrementing integer?
4. Why is `JobStatus.PENDING` better than the string `"pending"`?

Write your answers here first, then see if the code matches what you thought.

---

## Phase 2 — Async Execution

*(Populate when you reach Phase 2)*

### Pre-phase question

If `asyncio` runs on a single thread, how can multiple jobs run at the same time? What does "concurrent" actually mean here?

---

## Phase 3 — Postgres

*(Populate when you reach Phase 3)*

### Pre-phase question

Your Phase 1 `Job` dataclass had certain fields. Which of those will map cleanly to Postgres columns? Which ones are wrong or need to change? Why?

---

## Phase 4 — Redis Queue

*(Populate when you reach Phase 4)*

### Pre-phase question

What happens between the moment `POST /jobs` returns and the moment a worker starts executing the job? Who holds the job during that window?

---

## Phase 5 — Multiple Workers

*(Populate when you reach Phase 5)*

### Pre-phase question

You have 3 workers and 1 job. All 3 workers see the job as `PENDING` at the same millisecond. Without any locking mechanism, what happens? Walk through it step by step.

---

## Phase 6 — Rate Limiting

*(Populate when you reach Phase 6)*

### Pre-phase question

Two workers call the token bucket Lua script simultaneously for the same tenant. Redis is single-threaded. What actually happens? In what order?

---

## Phase 7 — Multi-Tenancy and Failures

*(Populate when you reach Phase 7)*

---

## Phase 8 — Observability

*(Populate when you reach Phase 8)*

---

## Phase 9 — Load Testing

*(Populate when you reach Phase 9)*

---

## Things I Got Wrong (Running List)

*(Add here as you go — this is the most valuable section)*

| Phase | What I assumed | What actually happened | What I learned |
|---|---|---|---|
| | | | |

---

## Concepts I Had to Look Up More Than Once

*(If you looked something up twice, write a one-line summary here so you don't look it up a third time)*

| Concept | One-line summary |
|---|---|
| | |
