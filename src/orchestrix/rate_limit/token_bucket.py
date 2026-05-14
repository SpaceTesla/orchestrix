import time
from typing import TypedDict


class TokenBucketResult(TypedDict):
    allowed: bool
    remaining_tokens: float


class TokenBucket:
    def __init__(
        self,
        max_tokens: float,
        refill_rate: float,
    ) -> None:
        # Maximum burst capacity
        self.max_tokens = max_tokens

        # Tokens regenerated per second
        self.refill_rate = refill_rate

        # Start with a full bucket
        self.tokens = max_tokens

        # Timestamp of last refill calculation
        self.last_refill = time.time()

    def _try_consume(
        self,
        tokens_requested: float,
    ) -> TokenBucketResult:
        if self.tokens >= tokens_requested:
            # Consume tokens
            self.tokens -= tokens_requested

            return {
                "allowed": True,
                "remaining_tokens": self.tokens,
            }

        return {
            "allowed": False,
            "remaining_tokens": self.tokens,
        }

    def allow(
        self,
        tokens_requested: float = 1,
    ) -> TokenBucketResult:
        # Current timestamp
        now = time.time()

        # Time elapsed since last refill
        elapsed_time = now - self.last_refill

        # Calculate regenerated tokens
        tokens_to_add = elapsed_time * self.refill_rate

        # Refill bucket while respecting max capacity
        self.tokens = min(
            self.tokens + tokens_to_add,
            self.max_tokens,
        )

        # Update refill timestamp
        self.last_refill = now

        # Attempt token consumption
        return self._try_consume(tokens_requested)
