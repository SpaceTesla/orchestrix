from fastapi import APIRouter, Depends
from typing import List
from fastapi import Query
import asyncpg

from orchestrix.api.deps import get_redis_queue, get_db_conn
from orchestrix.queue.redis_client import RedisQueue
from orchestrix.api.schemas import JobCreateRequest, JobResponse
from orchestrix.db import queries


router = APIRouter()


@router.post("/jobs", response_model=JobResponse)
async def create_jobs(
    request: JobCreateRequest,
    queue: RedisQueue = Depends(get_redis_queue),
    conn: asyncpg.Connection = Depends(get_db_conn),
):
    # Step 1 - insert into db
    job = await queries.create_job(
        conn, job_type=request.job_type, payload=request.payload
    )

    # Step 2 - enqueue (insert to redis stream)
    await queue.enqueue(str(job["id"]))

    return JobResponse(
        id=str(job["id"]),
        status=job.get("status"),
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    conn: asyncpg.Connection = Depends(get_db_conn),
):
    job = await queries.get_job(conn, job_id)

    if not job:
        return {"id": job_id, "status": "not_found"}

    return JobResponse(
        id=str(job["id"]),
        status=job["status"],
    )


@router.get("/jobs", response_model=List[JobResponse])
async def list_jobs(
    limit: int = Query(20, le=100),
    status: str | None = Query(None),
    conn: asyncpg.Connection = Depends(get_db_conn),
):
    rows = await queries.list_jobs(conn, limit=limit, status=status)

    return [
        JobResponse(
            id=str(row["id"]),
            status=row["status"],
        )
        for row in rows
    ]
