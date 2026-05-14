import asyncio
import time

from redis.asyncio import Redis

from orchestrix.rate_limit.redis_rate_limiter import (
    RedisRateLimiter,
)


TOTAL_REQUESTS = 50


async def main() -> None:
    # -----------------------------------------
    # Redis setup
    # -----------------------------------------

    redis = Redis(
        host="redis",
        port=6379,
        decode_responses=True,
    )

    limiter = RedisRateLimiter(redis)

    tenant_id = "test-tenant"

    bucket_key = f"rate_limit:{tenant_id}"

    # -----------------------------------------
    # Reset bucket state
    # -----------------------------------------

    await redis.delete(bucket_key)

    print("\n=== Atomic Lua Rate Limit Test ===\n")

    # -----------------------------------------
    # Concurrent request task
    # -----------------------------------------

    async def attempt_request(
        request_id: int,
    ) -> bool:
        result = await limiter.allow(
            tenant_id=tenant_id,
            max_tokens=1,
            refill_rate=0,
        )

        print(
            f"[{time.time():.4f}] "
            f"Request #{request_id:<2} | "
            f"allowed={result['allowed']:<5} | "
            f"remaining={result['remaining_tokens']:.2f} | "
            f"retry_after={result['retry_after']:.2f}"
        )

        return result["allowed"]

    # -----------------------------------------
    # Launch concurrent requests
    # -----------------------------------------

    tasks = [attempt_request(i) for i in range(1, TOTAL_REQUESTS + 1)]

    results = await asyncio.gather(*tasks)

    # -----------------------------------------
    # Final stats
    # -----------------------------------------

    allowed_count = sum(results)

    print("\n=== Final Results ===\n")

    print(f"Total Requests : {TOTAL_REQUESTS}")
    print(f"Allowed        : {allowed_count}")

    print("\nExpected allowed count = 1 (because max_tokens=1 and refill_rate=0)")

    if allowed_count == 1:
        print("\nSUCCESS: Atomic Lua script prevented the distributed race condition.")
    else:
        print("\nFAILURE: Atomicity broken. More than one request consumed the token.")

    # -----------------------------------------
    # Inspect final Redis bucket state
    # -----------------------------------------

    final_bucket = await redis.hgetall(bucket_key)

    print("\n=== Final Redis Bucket State ===\n")

    print(final_bucket)

    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
