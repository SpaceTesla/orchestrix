import asyncio
import socket
import os

from orchestrix.queue.redis_client import RedisQueue
from orchestrix.db.pool import init_pool, get_pool
from orchestrix.db import queries
from orchestrix.config import settings


def get_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


async def _process_message(
    *,
    queue: RedisQueue,
    pool,
    worker_id: str,
    message_id: str,
    data: dict,
) -> None:
    job_id = data["job_id"]

    print(f"[{worker_id}] Received {job_id}")

    async with pool.acquire() as conn:
        # Step 1 — claim job (critical)
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

            # TEMP handler
            print(f"[{worker_id}] Executing {job['id']}")
            await asyncio.sleep(1)
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

            # Still ACK so it doesn't loop forever
            await queue.ack(message_id)


async def _drain_autoclaim(
    *,
    queue: RedisQueue,
    pool,
    worker_id: str,
    min_idle_time_ms: int,
    count: int,
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
        )

    return len(reclaimed)


async def worker():
    await init_pool()

    queue = RedisQueue(settings.redis_url)
    await queue.create_group()

    worker_id = get_worker_id()

    print(f"[{worker_id}] Worker started")

    pool = get_pool()

    while True:
        messages = await queue.read(worker_id, count=5)

        if not messages:
            # Phase 4 success criteria: on restart, reclaim PEL entries via XAUTOCLAIM.
            # We also do this during idle periods to recover stuck messages.
            reclaimed = await _drain_autoclaim(
                queue=queue,
                pool=pool,
                worker_id=worker_id,
                min_idle_time_ms=30_000,
                count=10,
            )
            if reclaimed:
                print(f"[{worker_id}] Reclaimed {reclaimed} pending messages")
            continue

        for message_id, data in messages:
            await _process_message(
                queue=queue,
                pool=pool,
                worker_id=worker_id,
                message_id=message_id,
                data=data,
            )


if __name__ == "__main__":
    asyncio.run(worker())
