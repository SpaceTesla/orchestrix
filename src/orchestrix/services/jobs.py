from dataclasses import dataclass

from asyncpg import Connection, Record
from asyncpg.exceptions import UniqueViolationError

from orchestrix.db import queries
from orchestrix.queue.redis_client import RedisQueue
from orchestrix.services.exceptions import JobNotFoundError


@dataclass(frozen=True)
class CreateJobResult:
    job_id: str
    status: str
    was_created: bool


async def create_job(
    conn: Connection,
    queue: RedisQueue,
    *,
    tenant_id: str,
    job_type: str,
    payload: dict,
    idempotency_key: str,
) -> CreateJobResult:
    existing = await queries.get_job_by_idempotency_key(
        conn, tenant_id, idempotency_key
    )
    if existing:
        return CreateJobResult(
            job_id=str(existing["id"]),
            status=str(existing["status"]),
            was_created=False,
        )

    try:
        job = await queries.create_job(
            conn,
            tenant_id=tenant_id,
            job_type=job_type,
            payload=payload,
            idempotency_key=idempotency_key,
        )
    except UniqueViolationError:
        existing = await queries.get_job_by_idempotency_key(
            conn, tenant_id, idempotency_key
        )
        if existing is None:
            raise
        return CreateJobResult(
            job_id=str(existing["id"]),
            status=str(existing["status"]),
            was_created=False,
        )

    await queue.enqueue(str(job["id"]))
    return CreateJobResult(
        job_id=str(job["id"]),
        status=str(job["status"]),
        was_created=True,
    )


async def get_job(conn: Connection, job_id: str) -> Record:
    job = await queries.get_job(conn, job_id)
    if job is None:
        raise JobNotFoundError(job_id)
    return job


async def list_jobs(
    conn: Connection,
    *,
    limit: int = 20,
    status: str | None = None,
) -> list[Record]:
    return await queries.list_jobs(conn, limit=limit, status=status)
