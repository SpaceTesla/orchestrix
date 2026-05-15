import asyncio
import os
import socket

from redis.asyncio import Redis

from orchestrix.cache.tenant_config_cache import TenantConfigCache
from orchestrix.config import settings
from orchestrix.db import queries
from orchestrix.db.pool import get_pool, init_pool
from orchestrix.queue.redis_client import RedisQueue
from orchestrix.rate_limit.gate import wait_until_allowed
from orchestrix.rate_limit.redis_rate_limiter import RedisRateLimiter


def get_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


async def _process_message(
    *,
    queue: RedisQueue,
    pool,
    worker_id: str,
    message_id: str,
    data: dict,
    limiter: RedisRateLimiter,
    tenant_cache: TenantConfigCache,
) -> None:
    job_id = data["job_id"]

    print(f"[{worker_id}] Received {job_id}")

    async with pool.acquire() as conn:
        job = await queries.get_job(conn, job_id)

    if job is None:
        print(f"[{worker_id}] Job not found {job_id}, acking")
        await queue.ack(message_id)
        return

    if job["status"] != "pending":
        print(
            f"[{worker_id}] Skipping {job_id} (status={job['status']}), acking"
        )
        await queue.ack(message_id)
        return

    tenant_id = str(job["tenant_id"])
    tenant_config = await tenant_cache.get_tenant_config(tenant_id)

    await wait_until_allowed(
        limiter,
        tenant_id=tenant_id,
        max_tokens=tenant_config["burst_capacity"],
        refill_rate=tenant_config["rate_limit_rps"],
    )

    async with pool.acquire() as conn:
        claimed = await queries.transition_status(
            conn,
            job_id=job_id,
            old_status="pending",
            new_status="running",
            worker_id=worker_id,
        )

        if not claimed:
            print(f"[{worker_id}] Lost race for {job_id}")
            await queue.ack(message_id)
            return

        try:
            job = await queries.get_job(conn, job_id)

            print(f"[{worker_id}] Executing {job['id']}")
            await asyncio.sleep(10)
            await queries.transition_status(
                conn,
                job_id=job_id,
                old_status="running",
                new_status="success",
                worker_id=worker_id,
            )

            await queue.ack(message_id)

            print(f"[{worker_id}] Completed {job['id']}")
        except Exception as e:
            print(f"[{worker_id}] Failed {job['id']}: {e}")

            await queries.transition_status(
                conn,
                job_id=job_id,
                old_status="running",
                new_status="failed",
                worker_id=worker_id,
                error_message=str(e),
            )

            await queue.ack(message_id)


async def _drain_autoclaim(
    *,
    queue: RedisQueue,
    pool,
    worker_id: str,
    min_idle_time_ms: int,
    count: int,
    limiter: RedisRateLimiter,
    tenant_cache: TenantConfigCache,
) -> int:
    reclaimed = await queue.autoclaim(
        consumer_name=worker_id,
        min_idle_time=min_idle_time_ms,
        count=count,
    )

    if not reclaimed:
        return 0

    for message_id, data in reclaimed:
        await _process_message(
            queue=queue,
            pool=pool,
            worker_id=worker_id,
            message_id=message_id,
            data=data,
            limiter=limiter,
            tenant_cache=tenant_cache,
        )

    return len(reclaimed)


async def worker() -> None:
    await init_pool()

    queue = RedisQueue(settings.redis_url)
    await queue.create_group()

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    limiter = RedisRateLimiter(redis)
    tenant_cache = TenantConfigCache(redis)

    worker_id = get_worker_id()

    print(f"[{worker_id}] Worker started")

    pool = get_pool()

    try:
        while True:
            messages = await queue.read(worker_id, count=5)

            if not messages:
                reclaimed = await _drain_autoclaim(
                    queue=queue,
                    pool=pool,
                    worker_id=worker_id,
                    min_idle_time_ms=30_000,
                    count=10,
                    limiter=limiter,
                    tenant_cache=tenant_cache,
                )
                if reclaimed:
                    print(
                        f"[{worker_id}] Reclaimed {reclaimed} pending messages"
                    )
                continue

            for message_id, data in messages:
                await _process_message(
                    queue=queue,
                    pool=pool,
                    worker_id=worker_id,
                    message_id=message_id,
                    data=data,
                    limiter=limiter,
                    tenant_cache=tenant_cache,
                )
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(worker())
