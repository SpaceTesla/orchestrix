import asyncio
import time

from redis.asyncio import Redis

from orchestrix.rate_limit.backoff import sleep_retry_after_with_jitter
from orchestrix.rate_limit.redis_rate_limiter import RedisRateLimiter


WORKERS = 40
MAX_ROUNDS = 200


async def worker(worker_id: int, limiter: RedisRateLimiter) -> tuple[int, int]:
    attempts = 0
    for _ in range(MAX_ROUNDS):
        attempts += 1
        result = await limiter.allow(
            tenant_id="jitter-tenant",
            max_tokens=2.0,
            refill_rate=5.0,
            tokens_requested=1.0,
        )
        if result["allowed"]:
            return worker_id, attempts
        await sleep_retry_after_with_jitter(result["retry_after"])
    return worker_id, attempts


async def main() -> None:
    redis = Redis(
        host="redis",
        port=6379,
        decode_responses=True,
    )
    limiter = RedisRateLimiter(redis)
    await redis.delete("rate_limit:jitter-tenant")

    print("\n=== Rate limit backoff + jitter (no busy-spin) ===\n")

    t0 = time.perf_counter()
    outcomes = await asyncio.gather(*[worker(i, limiter) for i in range(WORKERS)])
    dt = time.perf_counter() - t0

    total_attempts = sum(a for _, a in outcomes)
    successes = sum(1 for _, a in outcomes if a < MAX_ROUNDS)

    print(f"workers={WORKERS} duration_s={dt:.2f}")
    print(f"total allow() calls={total_attempts} workers_succeeded={successes}")

    if successes != WORKERS:
        print("FAILURE: some workers hit MAX_ROUNDS without being allowed.")
    else:
        print("SUCCESS: all workers acquired a token with bounded retries.")

    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
