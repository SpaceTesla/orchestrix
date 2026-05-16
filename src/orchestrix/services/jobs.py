from dataclasses import dataclass

from asyncpg import Connection, Record
from asyncpg.exceptions import UniqueViolationError

from orchestrix.core.logging import get_logger
from orchestrix.core.metrics import record_job_submitted
from orchestrix.db import queries
from orchestrix.queue.priority import JobPriority
from orchestrix.queue.redis_client import RedisQueue
from orchestrix.services.exceptions import JobNotFoundError

log = get_logger(__name__)


@dataclass(frozen=True)
class CreateJobResult:
    job: Record
    was_created: bool

    @property
    def job_id(self) -> str:
        return str(self.job["id"])


async def create_job(
    conn: Connection,
    queue: RedisQueue,
    *,
    tenant_id: str,
    job_type: str,
    payload: dict,
    idempotency_key: str,
    priority: JobPriority = JobPriority.NORMAL,
) -> CreateJobResult:
    existing = await queries.get_job_by_idempotency_key(
        conn, tenant_id, idempotency_key
    )
    if existing:
        job = await queries.get_job(conn, str(existing["id"]))
        if job is None:
            raise RuntimeError(f"idempotency key references missing job {existing['id']}")
        log.info(
            "job_idempotent_replay",
            job_id=str(job["id"]),
            tenant_id=tenant_id,
            job_type=job_type,
            priority=priority.value,
        )
        return CreateJobResult(job=job, was_created=False)

    try:
        job = await queries.create_job(
            conn,
            tenant_id=tenant_id,
            job_type=job_type,
            payload=payload,
            idempotency_key=idempotency_key,
            priority=priority.value,
        )
    except UniqueViolationError:
        existing = await queries.get_job_by_idempotency_key(
            conn, tenant_id, idempotency_key
        )
        if existing is None:
            raise
        job = await queries.get_job(conn, str(existing["id"]))
        if job is None:
            raise RuntimeError(f"idempotency key references missing job {existing['id']}")
        log.info(
            "job_idempotent_replay",
            job_id=str(job["id"]),
            tenant_id=tenant_id,
            job_type=job_type,
            priority=priority.value,
        )
        return CreateJobResult(job=job, was_created=False)

    await queue.enqueue(str(job["id"]), priority)
    full_job = await queries.get_job(conn, str(job["id"]))
    if full_job is None:
        raise RuntimeError(f"job {job['id']} missing immediately after insert")
    log.info(
        "job_created",
        job_id=str(full_job["id"]),
        tenant_id=tenant_id,
        job_type=job_type,
        priority=priority.value,
    )
    record_job_submitted(tenant_id=tenant_id, priority=priority.value)
    return CreateJobResult(job=full_job, was_created=True)


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
