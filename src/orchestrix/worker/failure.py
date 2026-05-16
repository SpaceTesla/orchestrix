from datetime import datetime, timedelta, timezone

from asyncpg import Record

from orchestrix.config import settings
from orchestrix.core.logging import get_logger
from orchestrix.db import queries
from orchestrix.queue.redis_client import RedisQueue
from orchestrix.retry.backoff import compute_retry_delay_seconds, should_retry

log = get_logger(__name__)


async def handle_job_failure(
    conn,
    *,
    queue: RedisQueue,
    worker_id: str,
    job: Record,
    error_message: str,
) -> str:
    """
    Decide retry vs DEAD after a failed execution attempt.

    attempt_count is incremented when the job transitions to RUNNING.
    Returns: "retry_scheduled" | "job_dead" | "lost_race"
    """
    job_id = str(job["id"])
    attempt_count = int(job["attempt_count"])
    max_attempts = int(job["max_attempts"])

    if should_retry(attempt_count, max_attempts):
        delay_seconds = compute_retry_delay_seconds(
            attempt_count,
            base_delay=settings.retry_base_delay_seconds,
            max_delay=settings.retry_max_delay_seconds,
        )
        scheduled_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)

        scheduled = await queries.schedule_job_retry(
            conn,
            job_id,
            worker_id=worker_id,
            scheduled_at=scheduled_at,
            error_message=error_message,
            backoff_seconds=delay_seconds,
        )
        if not scheduled:
            return "lost_race"

        await queue.enqueue(job_id, str(job["priority"]))
        log.info(
            "job_retry_scheduled",
            delay_seconds=round(delay_seconds, 2),
            scheduled_at=scheduled_at.isoformat(),
            max_attempts=max_attempts,
        )
        return "retry_scheduled"

    marked = await queries.mark_job_dead(
        conn,
        job_id,
        worker_id=worker_id,
        error_message=error_message,
    )
    if not marked:
        return "lost_race"

    log.warning(
        "job_marked_dead",
        error_message=error_message,
        max_attempts=max_attempts,
    )
    return "job_dead"
