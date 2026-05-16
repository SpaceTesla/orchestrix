import asyncio

from orchestrix.config import settings
from orchestrix.core.logging import get_logger
from orchestrix.db import queries
from orchestrix.queue.redis_client import RedisQueue

log = get_logger(__name__)


async def reap_orphaned_jobs(
    *,
    pool,
    queue: RedisQueue,
    reaper_id: str,
) -> int:
    """Find stale RUNNING jobs and reclaim them. Returns count reaped."""
    async with pool.acquire() as conn:
        candidates = await queries.list_stale_running_jobs(
            conn,
            threshold_seconds=settings.reaper_threshold_seconds,
            limit=settings.reaper_batch_size,
        )

    if not candidates:
        return 0

    reaped = 0
    for row in candidates:
        job_id = str(row["id"])
        async with pool.acquire() as conn:
            result = await queries.reap_orphaned_job(
                conn,
                job_id,
                threshold_seconds=settings.reaper_threshold_seconds,
                reaper_id=reaper_id,
                previous_worker_id=row["worker_id"],
            )

        if result is None:
            continue

        reaped += 1
        new_status = result["status"]
        if new_status == "pending":
            await queue.enqueue(job_id, str(result["priority"]))

        log.info(
            "job_reaped",
            job_id=job_id,
            tenant_id=str(row["tenant_id"]),
            worker_id=reaper_id,
            attempt_count=int(result["attempt_count"]),
            previous_worker=row["worker_id"],
            new_status=new_status,
            max_attempts=int(result["max_attempts"]),
        )

    return reaped


async def reaper_loop(
    *,
    pool,
    queue: RedisQueue,
    reaper_id: str,
    shutdown: asyncio.Event,
) -> None:
    reaper_log = log.bind(worker_id=reaper_id, component="reaper")
    reaper_log.info(
        "reaper_started",
        interval_seconds=settings.reaper_interval_seconds,
        threshold_seconds=settings.reaper_threshold_seconds,
    )

    while not shutdown.is_set():
        try:
            count = await reap_orphaned_jobs(
                pool=pool,
                queue=queue,
                reaper_id=reaper_id,
            )
            if count:
                reaper_log.info("reaper_cycle_complete", reaped_count=count)
        except Exception:
            reaper_log.error("reaper_error", exc_info=True)

        try:
            await asyncio.wait_for(
                shutdown.wait(),
                timeout=settings.reaper_interval_seconds,
            )
        except asyncio.TimeoutError:
            continue

    reaper_log.info("reaper_stopped")
