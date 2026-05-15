from orchestrix.rate_limit.backoff import sleep_retry_after_with_jitter
from orchestrix.rate_limit.redis_rate_limiter import RateLimitResult, RedisRateLimiter


async def wait_until_allowed(
    limiter: RedisRateLimiter,
    *,
    tenant_id: str,
    max_tokens: float,
    refill_rate: float,
    tokens_requested: float = 1.0,
) -> RateLimitResult:
    """Block until the limiter grants tokens; backoff with jitter on each deny."""
    while True:
        result = await limiter.allow(
            tenant_id=tenant_id,
            max_tokens=max_tokens,
            refill_rate=refill_rate,
            tokens_requested=tokens_requested,
        )
        if result["allowed"]:
            return result
        await sleep_retry_after_with_jitter(result["retry_after"])
