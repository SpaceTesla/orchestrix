import time
from pathlib import Path
from typing import TypedDict

from redis.asyncio import Redis


class RateLimitResult(TypedDict):
    allowed: bool
    remaining_tokens: float
    retry_after: float


class RedisRateLimiter:
    def __init__(
        self,
        redis_client: Redis,
    ) -> None:
        self.redis = redis_client

        # Load Lua script
        lua_script_path = Path(__file__).parent / "lua" / "token_bucket.lua"

        with open(lua_script_path, "r") as f:
            lua_script = f.read()

        # Register Lua script
        self.token_bucket_script = self.redis.register_script(lua_script)

    async def allow(
        self,
        tenant_id: str,
        max_tokens: float,
        refill_rate: float,
        tokens_requested: float = 1,
    ) -> RateLimitResult:
        # Redis bucket key
        bucket_key = f"rate_limit:{tenant_id}"

        # Execute Lua script atomically
        result = await self.token_bucket_script(
            keys=[bucket_key],
            args=[
                time.time(),
                max_tokens,
                refill_rate,
                tokens_requested,
            ],
        )

        # Parse Lua response
        allowed = bool(result[0])

        remaining_tokens = float(result[1])

        retry_after = float(result[2])

        return {
            "allowed": allowed,
            "remaining_tokens": remaining_tokens,
            "retry_after": retry_after,
        }
