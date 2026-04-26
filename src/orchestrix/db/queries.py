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
            SET status = $3,
                worker_id = $4,
                started_at = CASE 
                    WHEN $3 = 'running' THEN NOW() 
                    ELSE started_at 
                END,
                completed_at = CASE 
                    WHEN $3 IN ('success', 'failed', 'dead') THEN NOW()
                    ELSE completed_at
                END,
                error_message = $5
            WHERE id = $1 AND status = $2
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


async def fetch_next_job(conn) -> Optional[Record]:
    """Pick the pending job scheduled first"""
    return await conn.fetchrow(
        """
        SELECT *
        FROM jobs
        WHERE status = 'pending'
          AND scheduled_at <= NOW()
        ORDER BY scheduled_at ASC
        LIMIT 1
    """
    )
