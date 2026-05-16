import asyncio

from orchestrix.config import settings
from orchestrix.db import queries
from orchestrix.queue.redis_client import RedisQueue


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

        print(
            f"[{reaper_id}] reaped job_id={job_id} "
            f"previous_worker={row['worker_id']} "
            f"new_status={new_status} "
            f"attempt={result['attempt_count']}/{result['max_attempts']}"
        )

    return reaped


async def reaper_loop(
    *,
    pool,
    queue: RedisQueue,
    reaper_id: str,
    shutdown: asyncio.Event,
) -> None:
    print(
        f"[{reaper_id}] Reaper started "
        f"(interval={settings.reaper_interval_seconds}s, "
        f"threshold={settings.reaper_threshold_seconds}s)"
    )

    while not shutdown.is_set():
        try:
            count = await reap_orphaned_jobs(
                pool=pool,
                queue=queue,
                reaper_id=reaper_id,
            )
            if count:
                print(f"[{reaper_id}] Reaper cycle reclaimed {count} job(s)")
        except Exception as e:
            print(f"[{reaper_id}] Reaper error: {e}")

        try:
            await asyncio.wait_for(
                shutdown.wait(),
                timeout=settings.reaper_interval_seconds,
            )
        except asyncio.TimeoutError:
            continue

    print(f"[{reaper_id}] Reaper stopped")
