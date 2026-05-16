from orchestrix.core.logging import get_logger
from orchestrix.core.metrics import record_rate_limit_rejection
from orchestrix.rate_limit.backoff import sleep_retry_after_with_jitter
from orchestrix.rate_limit.redis_rate_limiter import RateLimitResult, RedisRateLimiter

log = get_logger(__name__)


async def wait_until_allowed(
    limiter: RedisRateLimiter,
    *,
    tenant_id: str,
    max_tokens: float,
    refill_rate: float,
    tokens_requested: float = 1.0,
) -> RateLimitResult:
    """Block until the limiter grants tokens; backoff with jitter on each deny."""
    denial_count = 0

    while True:
        result = await limiter.allow(
            tenant_id=tenant_id,
            max_tokens=max_tokens,
            refill_rate=refill_rate,
            tokens_requested=tokens_requested,
        )
        if result["allowed"]:
            if denial_count:
                log.debug(
                    "rate_limit_granted",
                    tenant_id=tenant_id,
                    denial_count=denial_count,
                )
            return result

        denial_count += 1
        retry_after = result["retry_after"]

        if denial_count == 1:
            log.debug(
                "rate_limit_waiting",
                tenant_id=tenant_id,
                retry_after=retry_after,
            )

        log.warning(
            "rate_limit_denied",
            tenant_id=tenant_id,
            retry_after=retry_after,
            denial_count=denial_count,
        )
        record_rate_limit_rejection(tenant_id=tenant_id)
        await sleep_retry_after_with_jitter(retry_after)
