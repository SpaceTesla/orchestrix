from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from typing import List
from fastapi import Query
import asyncpg

from orchestrix.api.deps import get_redis_queue, get_db_conn
from orchestrix.queue.redis_client import RedisQueue, get_redis_queue_instance
from orchestrix.api.schemas import (
    JobCreateRequest,
    JobResponse,
    HealthResponse,
    DependencyCheck,
    RootResponse,
)
from orchestrix.db import queries
from orchestrix.db.pool import get_pool


router = APIRouter()


@router.get("/", response_model=RootResponse)
async def root(request: Request) -> RootResponse:
    base = str(request.base_url).rstrip("/")
    return RootResponse(
        service=request.app.title,
        version=request.app.version,
        docs=f"{base}/docs",
        openapi=f"{base}/openapi.json",
        health=f"{base}/health",
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={
        503: {
            "model": HealthResponse,
            "description": "PostgreSQL or Redis check failed",
        }
    },
)
async def get_health():
    postgres_check = DependencyCheck(ok=True)
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception as e:
        postgres_check = DependencyCheck(ok=False, error=str(e))

    redis_check = DependencyCheck(ok=True)
    try:
        queue = get_redis_queue_instance()
        await queue.redis.ping()
    except Exception as e:
        redis_check = DependencyCheck(ok=False, error=str(e))

    healthy = postgres_check.ok and redis_check.ok
    body = HealthResponse(
        status="healthy" if healthy else "unhealthy",
        postgres=postgres_check,
        redis=redis_check,
    )
    if not healthy:
        return JSONResponse(status_code=503, content=body.model_dump())
    return body


@router.post("/jobs", response_model=JobResponse)
async def create_jobs(
    request: JobCreateRequest,
    queue: RedisQueue = Depends(get_redis_queue),
    conn: asyncpg.Connection = Depends(get_db_conn),
):
    # Step 1 - insert into db
    job = await queries.create_job(
        conn,
        tenant_id=str(request.tenant_id),
        job_type=request.job_type,
        payload=request.payload,
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
