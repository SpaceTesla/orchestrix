import random


def compute_retry_delay_seconds(
    attempt_count: int,
    *,
    base_delay: float,
    max_delay: float,
    rng: random.Random | None = None,
) -> float:
    """
    Exponential backoff with jitter for job retries.

    backoff = min(2 ** attempt_count * base_delay, max_delay)
    delay = backoff + uniform(0, backoff * 0.1)
    """
    if attempt_count < 1:
        raise ValueError("attempt_count must be >= 1 for retry backoff")

    backoff = min((2**attempt_count) * base_delay, max_delay)
    jitter_source = rng if rng is not None else random
    jitter = jitter_source.uniform(0, backoff * 0.1)
    return backoff + jitter


def should_retry(attempt_count: int, max_attempts: int) -> bool:
    return attempt_count < max_attempts
