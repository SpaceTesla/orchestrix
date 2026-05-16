from asyncpg import Connection, Record
from typing import Optional
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
