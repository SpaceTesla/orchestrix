"""
Verify the Redis token bucket enforces sustained RPS ≈ refill_rate.

Uses one pacer: on deny, sleeps retry_after with zero jitter so wall-clock
time tracks the limiter's math. Burst allows happen back-to-back; after that,
elapsed time should be at least (N - burst) / rps (with small clock slack).
"""

import asyncio
import time

from redis.asyncio import Redis

from orchestrix.rate_limit.backoff import sleep_retry_after_with_jitter
from orchestrix.rate_limit.redis_rate_limiter import RedisRateLimiter


TENANT_ID = "rps-verify-tenant"
TARGET_RPS = 10.0
BURST_CAPACITY = 5.0
TOTAL_ALLOWS = 45
# Minimum time to emit TOTAL_ALLOWS tokens: burst first, then (TOTAL - BURST) / rps
MIN_EXPECTED_SEC = (TOTAL_ALLOWS - BURST_CAPACITY) / TARGET_RPS
LOWER_SLACK = 0.90
UPPER_SLACK = 1.35
UPPER_PAD_SEC = 1.0


async def collect_allows_sequential(
    limiter: RedisRateLimiter,
) -> float:
    """Wall seconds to observe TOTAL_ALLOWS successful allows."""
    allowed_count = 0
    t0 = time.perf_counter()
    while allowed_count < TOTAL_ALLOWS:
        result = await limiter.allow(
            tenant_id=TENANT_ID,
            max_tokens=BURST_CAPACITY,
            refill_rate=TARGET_RPS,
            tokens_requested=1.0,
        )
        if result["allowed"]:
            allowed_count += 1
        else:
            await sleep_retry_after_with_jitter(
                result["retry_after"],
                jitter_max=0.0,
            )
    return time.perf_counter() - t0


async def window_ceiling_many_workers(
    limiter: RedisRateLimiter,
    *,
    duration_sec: float,
    num_workers: int,
) -> int:
    """Greedy workers with backoff; global allows in window should not exceed burst + rps*T by much."""
    stop_at = time.perf_counter() + duration_sec
    total = 0
    lock = asyncio.Lock()

    async def worker() -> None:
        nonlocal total
        while time.perf_counter() < stop_at:
            result = await limiter.allow(
                tenant_id=TENANT_ID + ":window",
                max_tokens=3.0,
                refill_rate=TARGET_RPS,
                tokens_requested=1.0,
            )
            if result["allowed"]:
                async with lock:
                    total += 1
            else:
                await sleep_retry_after_with_jitter(
                    result["retry_after"],
                    jitter_max=0.02,
                )

    await asyncio.gather(*[worker() for _ in range(num_workers)])
    return total


async def main() -> None:
    redis = Redis(
        host="redis",
        port=6379,
        decode_responses=True,
    )
    limiter = RedisRateLimiter(redis)

    print("\n=== RPS sequential floor test ===\n")
    print(
        f"target_rps={TARGET_RPS} burst={BURST_CAPACITY} "
        f"total_allows={TOTAL_ALLOWS} min_expected_s≈{MIN_EXPECTED_SEC:.3f}"
    )

    await redis.delete(f"rate_limit:{TENANT_ID}")
    elapsed = await collect_allows_sequential(limiter)
    lower = MIN_EXPECTED_SEC * LOWER_SLACK
    upper = MIN_EXPECTED_SEC * UPPER_SLACK + UPPER_PAD_SEC

    print(f"elapsed_s={elapsed:.3f} (want >= {lower:.3f} and <= {upper:.3f})")

    if elapsed < lower:
        print("FAILURE: sustained allows faster than refill_rate (RPS too high).")
    elif elapsed > upper:
        print("FAILURE: slower than expected (check Redis/clock).")
    else:
        print("SUCCESS: wall time matches token-bucket RPS.")

    print("\n=== RPS window ceiling (many workers) ===\n")

    win_key = f"rate_limit:{TENANT_ID}:window"
    await redis.delete(win_key)

    duration_sec = 2.5
    burst = 3.0
    ceiling = burst + TARGET_RPS * duration_sec * 1.12
    count = await window_ceiling_many_workers(
        limiter,
        duration_sec=duration_sec,
        num_workers=24,
    )
    print(
        f"duration_s={duration_sec} workers=24 allows={count} "
        f"ceiling≈{ceiling:.1f} (burst + rps*T with margin)"
    )

    if count > ceiling:
        print("FAILURE: more allows than bucket can produce in the window.")
    else:
        print("SUCCESS: throughput did not exceed bucket capacity.")

    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
