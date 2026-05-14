import asyncio
import random


async def sleep_retry_after_with_jitter(
    retry_after: float,
    *,
    jitter_max: float = 0.1,
    min_when_unknown: float = 0.05,
) -> None:
    """
    Application-side backoff when rate-limited. Lua stays deterministic.

    retry_after < 0: no time-based refill (e.g. refill_rate == 0); use a
    small fixed delay plus jitter so workers do not tight-loop Redis.
    """
    if retry_after < 0:
        delay = min_when_unknown + random.uniform(0.0, jitter_max)
    else:
        delay = max(0.0, retry_after) + random.uniform(0.0, jitter_max)

    await asyncio.sleep(delay)
