import asyncio
from datetime import datetime, timezone

from asyncpg import Record


async def wait_until_eligible(job: Record, *, worker_id: str) -> None:
    """Block until job.scheduled_at <= now (delayed retry eligibility)."""
    scheduled_at = job["scheduled_at"]
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    if scheduled_at <= now:
        return

    delay_seconds = (scheduled_at - now).total_seconds()
    print(
        f"[{worker_id}] retry_attempt job_id={job['id']} "
        f"waiting_seconds={delay_seconds:.2f} scheduled_at={scheduled_at.isoformat()}"
    )
    await asyncio.sleep(delay_seconds)
