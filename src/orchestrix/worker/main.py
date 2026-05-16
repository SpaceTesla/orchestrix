import asyncio
import os
import socket

from redis.asyncio import Redis

from orchestrix.cache.tenant_config_cache import TenantConfigCache
from orchestrix.config import settings
from orchestrix.db import queries
from orchestrix.db.pool import get_pool, init_pool
from orchestrix.queue.priority import ALL_JOB_STREAMS
from orchestrix.queue.redis_client import RedisQueue
from orchestrix.handlers import execute, register_handlers
from orchestrix.worker.reaper import reaper_loop
from orchestrix.rate_limit.gate import wait_until_allowed
from orchestrix.rate_limit.redis_rate_limiter import RedisRateLimiter
from orchestrix.worker.failure import handle_job_failure
from orchestrix.worker.scheduling import wait_until_eligible


def get_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


async def _process_message(
    *,
    queue: RedisQueue,
    stream: str,
    pool,
    worker_id: str,
    message_id: str,
    data: dict,
    limiter: RedisRateLimiter,
    tenant_cache: TenantConfigCache,
) -> None:
    job_id = data["job_id"]

    print(f"[{worker_id}] Received {job_id} from {stream}")

    async with pool.acquire() as conn:
        job = await queries.get_job(conn, job_id)

    if job is None:
        print(f"[{worker_id}] Job not found {job_id}, acking")
        await queue.ack(stream, message_id)
        return

    if job["status"] != "pending":
        print(
            f"[{worker_id}] Skipping {job_id} (status={job['status']}), acking"
        )
        await queue.ack(stream, message_id)
        return

    await wait_until_eligible(job, worker_id=worker_id)

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
            await queue.ack(stream, message_id)
            return

        try:
            job = await queries.get_job(conn, job_id)

            print(
                f"[{worker_id}] Executing {job['id']} "
                f"(priority={job['priority']}, attempt={job['attempt_count'] + 1})"
            )

            async with asyncio.timeout(settings.job_timeout_seconds):
                await execute(str(job["job_type"]), job["payload"])

            await queries.transition_status(
                conn,
                job_id=job_id,
                old_status="running",
                new_status="success",
                worker_id=worker_id,
            )

            await queue.ack(stream, message_id)

            print(f"[{worker_id}] Completed {job['id']}")
        except TimeoutError:
            print(
                f"[{worker_id}] Failed {job['id']}: "
                f"timeout after {settings.job_timeout_seconds}s"
            )
            job_after_run = await queries.get_job(conn, job_id)
            if job_after_run is None:
                await queue.ack(stream, message_id)
                return

            await handle_job_failure(
                conn,
                queue=queue,
                worker_id=worker_id,
                job=job_after_run,
                error_message=f"timeout after {settings.job_timeout_seconds}s",
            )
            await queue.ack(stream, message_id)
        except Exception as e:
            print(f"[{worker_id}] Failed {job['id']}: {e}")

            job_after_run = await queries.get_job(conn, job_id)
            if job_after_run is None:
                await queue.ack(stream, message_id)
                return

            await handle_job_failure(
                conn,
                queue=queue,
                worker_id=worker_id,
                job=job_after_run,
                error_message=str(e),
            )

            await queue.ack(stream, message_id)


async def _drain_autoclaim(
    *,
    queue: RedisQueue,
    stream: str,
    pool,
    worker_id: str,
    min_idle_time_ms: int,
    count: int,
    limiter: RedisRateLimiter,
    tenant_cache: TenantConfigCache,
) -> int:
    reclaimed = await queue.autoclaim(
        stream=stream,
        consumer_name=worker_id,
        min_idle_time=min_idle_time_ms,
        count=count,
    )

    if not reclaimed:
        return 0

    for message_id, data in reclaimed:
        await _process_message(
            queue=queue,
            stream=stream,
            pool=pool,
            worker_id=worker_id,
            message_id=message_id,
            data=data,
            limiter=limiter,
            tenant_cache=tenant_cache,
        )

    return len(reclaimed)


async def worker() -> None:
    register_handlers()
    await init_pool()

    queue = RedisQueue(settings.redis_url)
    await queue.create_groups()

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    limiter = RedisRateLimiter(redis)
    tenant_cache = TenantConfigCache(redis)

    worker_id = get_worker_id()

    reaper_id = f"{worker_id}-reaper"
    shutdown = asyncio.Event()

    print(
        f"[{worker_id}] Worker started (weighted poll: 5 high / 3 normal / 1 low, "
        f"job_timeout={settings.job_timeout_seconds}s, "
        f"reaper_threshold={settings.reaper_threshold_seconds}s)"
    )

    pool = get_pool()
    reaper_task = asyncio.create_task(
        reaper_loop(
            pool=pool,
            queue=queue,
            reaper_id=reaper_id,
            shutdown=shutdown,
        ),
        name="reaper",
    )

    try:
        while True:
            stream = queue.next_poll_stream()
            messages = await queue.read(stream, worker_id, count=5)

            if not messages:
                reclaimed_total = 0
                for autoclaim_stream in ALL_JOB_STREAMS:
                    reclaimed = await _drain_autoclaim(
                        queue=queue,
                        stream=autoclaim_stream,
                        pool=pool,
                        worker_id=worker_id,
                        min_idle_time_ms=30_000,
                        count=10,
                        limiter=limiter,
                        tenant_cache=tenant_cache,
                    )
                    reclaimed_total += reclaimed
                if reclaimed_total:
                    print(
                        f"[{worker_id}] Reclaimed {reclaimed_total} pending messages"
                    )
                continue

            print(
                f"[{worker_id}] Polled {stream}, "
                f"dequeued {len(messages)} job(s)"
            )

            for message_id, data in messages:
                await _process_message(
                    queue=queue,
                    stream=stream,
                    pool=pool,
                    worker_id=worker_id,
                    message_id=message_id,
                    data=data,
                    limiter=limiter,
                    tenant_cache=tenant_cache,
                )
    finally:
        shutdown.set()
        reaper_task.cancel()
        try:
            await reaper_task
        except asyncio.CancelledError:
            pass
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(worker())
