from typing import TypedDict

from redis.asyncio import Redis

from orchestrix.core.logging import get_logger
from orchestrix.db.pool import get_pool

log = get_logger(__name__)

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
        cache_key = f"tenant_config:{tenant_id}"

        cached_config = await self.redis.hgetall(cache_key)

        if cached_config:
            log.debug("tenant_config_cache_hit", tenant_id=tenant_id)
            return {
                "rate_limit_rps": float(cached_config["rate_limit_rps"]),
                "burst_capacity": float(cached_config["burst_capacity"]),
            }

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

        log.debug("tenant_config_cache_miss", tenant_id=tenant_id)
        return config
