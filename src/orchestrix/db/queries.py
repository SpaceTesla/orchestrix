from datetime import datetime

from asyncpg import Connection, Record
from typing import Any, Optional
import json

async def transition_status(
    conn: Connection,
    job_id: str,
    old_status: str,
    new_status: str,
    worker_id: str | None = None,
    error_message: str | None = None,
) -> bool:
    async with conn.transaction():
        result = await conn.fetchrow(
            """
            UPDATE jobs
            SET status = $3::job_status,
                worker_id = $4,
                attempt_count = CASE
                    WHEN $3::job_status = 'running'::job_status THEN attempt_count + 1
                    ELSE attempt_count
                END,
                started_at = CASE
                    WHEN $3::job_status = 'running'::job_status THEN NOW()
                    ELSE started_at
                END,
                completed_at = CASE
                    WHEN $3::job_status IN (
                        'success'::job_status,
                        'failed'::job_status,
                        'dead'::job_status
                    ) THEN NOW()
                    ELSE completed_at
                END,
                error_message = $5
            WHERE id = $1 AND status = $2::job_status
            RETURNING id;
        """,
            job_id,
            old_status,
            new_status,
            worker_id,
            error_message,
        )

        if result is None:
            return False

        await conn.execute(
            """
            INSERT INTO job_events (
                job_id,
                event_type,
                old_status,
                new_status,
                worker_id,
                metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        """,
            job_id,
            "status_transition",
            old_status,
            new_status,
            worker_id,
            json.dumps({"error": error_message} if error_message else {}),
        )

        return True


async def _insert_job_event(
    conn: Connection,
    *,
    job_id: str,
    event_type: str,
    old_status: str | None,
    new_status: str | None,
    worker_id: str | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO job_events (
            job_id,
            event_type,
            old_status,
            new_status,
            worker_id,
            metadata
        )
        VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        """,
        job_id,
        event_type,
        old_status,
        new_status,
        worker_id,
        json.dumps(metadata or {}),
    )


async def schedule_job_retry(
    conn: Connection,
    job_id: str,
    *,
    worker_id: str | None,
    scheduled_at: datetime,
    error_message: str,
    backoff_seconds: float,
) -> bool:
    async with conn.transaction():
        result = await conn.fetchrow(
            """
            UPDATE jobs
            SET status = 'pending'::job_status,
                scheduled_at = $2,
                worker_id = NULL,
                started_at = NULL,
                completed_at = NULL,
                error_message = $3,
                updated_at = NOW()
            WHERE id = $1 AND status = 'running'::job_status
            RETURNING id, attempt_count, max_attempts;
            """,
            job_id,
            scheduled_at,
            error_message,
        )

        if result is None:
            return False

        await _insert_job_event(
            conn,
            job_id=job_id,
            event_type="retry_scheduled",
            old_status="running",
            new_status="pending",
            worker_id=worker_id,
            metadata={
                "error": error_message,
                "backoff_seconds": backoff_seconds,
                "scheduled_at": scheduled_at.isoformat(),
                "attempt_count": result["attempt_count"],
                "max_attempts": result["max_attempts"],
            },
        )

        return True


async def mark_job_dead(
    conn: Connection,
    job_id: str,
    *,
    worker_id: str | None,
    error_message: str,
) -> bool:
    async with conn.transaction():
        result = await conn.fetchrow(
            """
            UPDATE jobs
            SET status = 'dead'::job_status,
                worker_id = $2,
                completed_at = NOW(),
                error_message = $3,
                updated_at = NOW()
            WHERE id = $1 AND status = 'running'::job_status
            RETURNING id, attempt_count, max_attempts;
            """,
            job_id,
            worker_id,
            error_message,
        )

        if result is None:
            return False

        await _insert_job_event(
            conn,
            job_id=job_id,
            event_type="job_dead",
            old_status="running",
            new_status="dead",
            worker_id=worker_id,
            metadata={
                "error": error_message,
                "attempt_count": result["attempt_count"],
                "max_attempts": result["max_attempts"],
            },
        )

        return True


async def create_job(
    conn: Connection,
    tenant_id: str,
    job_type: str,
    payload: dict,
    idempotency_key: str,
    priority: str = "normal",
) -> Record:
    return await conn.fetchrow(
        """
        INSERT INTO jobs (tenant_id, job_type, payload, idempotency_key, priority)
        VALUES ($1, $2, $3::jsonb, $4::uuid, $5)
        RETURNING id, status, priority
        """,
        tenant_id,
        job_type,
        json.dumps(payload),
        idempotency_key,
        priority,
    )


async def get_job(
    conn: Connection,
    job_id: str,
) -> Optional[Record]:
    return await conn.fetchrow(
        """
        SELECT *
        FROM jobs
        WHERE id = $1
        """,
        job_id,
    )


async def get_job_by_idempotency_key(
    conn: Connection,
    tenant_id: str,
    idempotency_key: str,
) -> Optional[Record]:
    return await conn.fetchrow(
        """
        SELECT id, status
        FROM jobs
        WHERE tenant_id = $1::uuid
          AND idempotency_key = $2::uuid
        """,
        tenant_id,
        idempotency_key,
    )


async def list_stale_running_jobs(
    conn: Connection,
    *,
    threshold_seconds: float,
    limit: int,
) -> list[Record]:
    return await conn.fetch(
        """
        SELECT id, tenant_id, priority, worker_id, attempt_count, started_at
        FROM jobs
        WHERE status = 'running'::job_status
          AND started_at < NOW() - ($1::double precision * INTERVAL '1 second')
        ORDER BY started_at ASC
        LIMIT $2
        """,
        threshold_seconds,
        limit,
    )


async def reap_orphaned_job(
    conn: Connection,
    job_id: str,
    *,
    threshold_seconds: float,
    reaper_id: str,
    previous_worker_id: str | None,
) -> Record | None:
    async with conn.transaction():
        result = await conn.fetchrow(
            """
            UPDATE jobs
            SET attempt_count = attempt_count + 1,
                status = CASE
                    WHEN attempt_count + 1 >= max_attempts THEN 'dead'::job_status
                    ELSE 'pending'::job_status
                END,
                worker_id = NULL,
                started_at = NULL,
                completed_at = CASE
                    WHEN attempt_count + 1 >= max_attempts THEN NOW()
                    ELSE NULL
                END,
                scheduled_at = NOW(),
                error_message = 'reaped: orphaned running job exceeded execution window',
                updated_at = NOW()
            WHERE id = $1
              AND status = 'running'::job_status
              AND started_at < NOW() - ($2::double precision * INTERVAL '1 second')
            RETURNING id, status, priority, attempt_count, max_attempts;
            """,
            job_id,
            threshold_seconds,
        )

        if result is None:
            return None

        await _insert_job_event(
            conn,
            job_id=job_id,
            event_type="reaped",
            old_status="running",
            new_status=str(result["status"]),
            worker_id=reaper_id,
            metadata={
                "previous_worker_id": previous_worker_id,
                "attempt_count": result["attempt_count"],
                "max_attempts": result["max_attempts"],
                "threshold_seconds": threshold_seconds,
            },
        )

        return result


async def list_jobs(
    conn,
    limit: int = 20,
    status: str | None = None,
):
    if status:
        return await conn.fetch(
            """
            SELECT id, job_type, status, priority, created_at
            FROM jobs
            WHERE status = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            status,
            limit,
        )

    return await conn.fetch(
        """
        SELECT id, job_type, status, priority, created_at
        FROM jobs
        ORDER BY created_at DESC
        LIMIT $1
        """,
        limit,
    )
