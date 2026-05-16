import asyncio
import os
import socket
import time

from redis.asyncio import Redis

from orchestrix.cache.tenant_config_cache import TenantConfigCache
from orchestrix.config import settings
from orchestrix.core.logging import (
    bind_job_context,
    clear_job_context,
    configure_logging,
    get_logger,
)
from orchestrix.core.metrics import (
    observe_job_attempts,
    observe_job_duration,
    record_job_completed,
    refresh_queue_depth,
    worker_active_jobs_dec,
    worker_active_jobs_inc,
)
from orchestrix.db import queries
from orchestrix.db.pool import get_pool, init_pool
from orchestrix.handlers import execute, register_handlers
from orchestrix.queue.priority import ALL_JOB_STREAMS
from orchestrix.queue.redis_client import RedisQueue
from orchestrix.rate_limit.gate import wait_until_allowed
from orchestrix.rate_limit.redis_rate_limiter import RedisRateLimiter
from orchestrix.worker.failure import handle_job_failure
from orchestrix.worker.metrics_server import start_worker_metrics_server
from orchestrix.worker.reaper import reaper_loop
from orchestrix.worker.scheduling import wait_until_eligible

log = get_logger(__name__)


def get_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


def _bind_job_from_record(job, *, worker_id: str) -> None:
    bind_job_context(
        job_id=str(job["id"]),
        tenant_id=str(job["tenant_id"]),
        worker_id=worker_id,
        attempt_count=int(job["attempt_count"]),
    )


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
    worker_log = log.bind(worker_id=worker_id, component="worker")
    job_id = data["job_id"]

    worker_log.debug(
        "job_message_received",
        job_id=job_id,
        stream=stream,
        message_id=message_id,
    )

    async with pool.acquire() as conn:
        job = await queries.get_job(conn, job_id)

    if job is None:
        worker_log.warning("job_not_found", job_id=job_id)
        await queue.ack(stream, message_id)
        return

    if job["status"] != "pending":
        worker_log.warning(
            "job_skipped_wrong_status",
            job_id=job_id,
            status=job["status"],
        )
        await queue.ack(stream, message_id)
        return

    _bind_job_from_record(job, worker_id=worker_id)
    try:
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
                worker_log.warning("job_claim_lost_race", job_id=job_id)
                await queue.ack(stream, message_id)
                return

            job = await queries.get_job(conn, job_id)
            if job is None:
                worker_log.warning("job_missing_after_claim", job_id=job_id)
                await queue.ack(stream, message_id)
                return

            _bind_job_from_record(job, worker_id=worker_id)

            job_type = str(job["job_type"])
            tenant_id = str(job["tenant_id"])
            attempt_count = int(job["attempt_count"])

            worker_log.info(
                "job_executing",
                job_type=job_type,
                priority=job["priority"],
                execution_attempt=attempt_count,
            )

            handler_started = False
            handler_start: float | None = None

            try:
                worker_active_jobs_inc(worker_id=worker_id)
                handler_started = True
                handler_start = time.perf_counter()

                async with asyncio.timeout(settings.job_timeout_seconds):
                    await execute(job_type, job["payload"])

                await queries.transition_status(
                    conn,
                    job_id=job_id,
                    old_status="running",
                    new_status="success",
                    worker_id=worker_id,
                )

                await queue.ack(stream, message_id)
                worker_log.info("job_completed")
                record_job_completed(
                    tenant_id=tenant_id,
                    job_type=job_type,
                    status="success",
                )
                observe_job_attempts(attempt_count)
            except TimeoutError:
                worker_log.error(
                    "job_timeout",
                    exc_info=True,
                    timeout_seconds=settings.job_timeout_seconds,
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
                worker_log.error(
                    "job_handler_failed",
                    exc_info=True,
                    error=str(e),
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
                    error_message=str(e),
                )

                await queue.ack(stream, message_id)
            finally:
                if handler_started and handler_start is not None:
                    observe_job_duration(
                        job_type=job_type,
                        duration_seconds=time.perf_counter() - handler_start,
                    )
                    worker_active_jobs_dec(worker_id=worker_id)
    finally:
        clear_job_context()


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
    configure_logging(
        log_level=settings.log_level,
        log_format=settings.log_format,
    )
    register_handlers()
    await init_pool()

    queue = RedisQueue(settings.redis_url)
    await queue.create_groups()

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    limiter = RedisRateLimiter(redis)
    tenant_cache = TenantConfigCache(redis)

    worker_id = get_worker_id()
    worker_log = log.bind(worker_id=worker_id, component="worker")

    start_worker_metrics_server(port=settings.metrics_worker_port)

    reaper_id = f"{worker_id}-reaper"
    shutdown = asyncio.Event()

    worker_log.info(
        "worker_started",
        job_timeout_seconds=settings.job_timeout_seconds,
        reaper_threshold_seconds=settings.reaper_threshold_seconds,
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
            await refresh_queue_depth(queue)

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
                    worker_log.info(
                        "messages_autoclaimed",
                        reclaimed_count=reclaimed_total,
                    )
                continue

            worker_log.debug(
                "stream_polled",
                stream=stream,
                dequeued_count=len(messages),
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
        worker_log.info("worker_stopped")
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(worker())
