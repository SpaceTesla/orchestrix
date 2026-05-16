from dataclasses import dataclass

from orchestrix.api.schemas import DependencyCheck, HealthResponse
from orchestrix.db.pool import get_pool
from orchestrix.queue.redis_client import get_redis_queue_instance


@dataclass(frozen=True)
class HealthCheckResult:
    body: HealthResponse
    healthy: bool


async def check_health() -> HealthCheckResult:
    postgres_check = DependencyCheck(ok=True)
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception as e:
        postgres_check = DependencyCheck(ok=False, error=str(e))

    redis_check = DependencyCheck(ok=True)
    try:
        queue = get_redis_queue_instance()
        await queue.redis.ping()
    except Exception as e:
        redis_check = DependencyCheck(ok=False, error=str(e))

    healthy = postgres_check.ok and redis_check.ok
    body = HealthResponse(
        status="healthy" if healthy else "unhealthy",
        postgres=postgres_check,
        redis=redis_check,
    )
    return HealthCheckResult(body=body, healthy=healthy)
