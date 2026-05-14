from typing import TypedDict

from redis.asyncio import Redis

from orchestrix.db.pool import get_pool


CACHE_TTL_SECONDS = 60


class TenantConfig(TypedDict):
    rate_limit_rps: float
    burst_capacity: float


class TenantConfigCache:
    def __init__(
        self,
        redis_client: Redis,
    ) -> None:
        self.redis = redis_client

    async def get_tenant_config(
        self,
        tenant_id: str,
    ) -> TenantConfig:
        # -----------------------------------------
        # Redis cache key
        # -----------------------------------------

        cache_key = f"tenant_config:{tenant_id}"

        # -----------------------------------------
        # Attempt cache read
        # -----------------------------------------

        cached_config = await self.redis.hgetall(cache_key)

        # -----------------------------------------
        # Cache hit
        # -----------------------------------------

        if cached_config:
            print("Cache found")
            return {
                "rate_limit_rps": float(cached_config["rate_limit_rps"]),
                "burst_capacity": float(cached_config["burst_capacity"]),
            }

        # -----------------------------------------
        # Cache miss → fetch from Postgres
        # -----------------------------------------

        pool = get_pool()

        row = await pool.fetchrow(
            """
            SELECT
                rate_limit_rps,
                burst_capacity
            FROM tenants
            WHERE id = $1
            """,
            tenant_id,
        )

        if row is None:
            raise ValueError(f"Tenant not found: {tenant_id}")

        config: TenantConfig = {
            "rate_limit_rps": float(row["rate_limit_rps"]),
            "burst_capacity": float(row["burst_capacity"]),
        }

        # -----------------------------------------
        # Store in Redis cache
        # -----------------------------------------

        await self.redis.hset(
            cache_key,
            mapping={
                "rate_limit_rps": config["rate_limit_rps"],
                "burst_capacity": config["burst_capacity"],
            },
        )

        await self.redis.expire(
            cache_key,
            CACHE_TTL_SECONDS,
        )

        # -----------------------------------------
        # Return config
        # -----------------------------------------

        return config
