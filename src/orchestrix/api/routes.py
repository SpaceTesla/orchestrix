from typing import Annotated, List
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request

from orchestrix.api.deps import get_db_conn, get_redis_queue
from orchestrix.api.mappers import job_to_response
from orchestrix.api.openapi import JOB_GET_RESPONSES, JOB_POST_RESPONSES
from orchestrix.api.responses import api_response
from orchestrix.api.schemas import (
    HealthResponse,
    JobCreateRequest,
    JobResponse,
    RootResponse,
)
from orchestrix.queue.redis_client import RedisQueue
from orchestrix.services import health as health_service
from orchestrix.services import jobs as job_service
from orchestrix.services.exceptions import JobNotFoundError
from orchestrix.services.root import build_root_response

router = APIRouter()


@router.get("/", response_model=RootResponse)
async def root(request: Request) -> RootResponse:
    return build_root_response(
        service=request.app.title,
        version=request.app.version,
        base_url=str(request.base_url),
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
    result = await health_service.check_health()
    if not result.healthy:
        return api_response(result.body, status_code=503)
    return result.body


@router.post(
    "/jobs",
    response_model=JobResponse,
    status_code=201,
    responses=JOB_POST_RESPONSES,
)
async def create_job(
    request: JobCreateRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    queue: RedisQueue = Depends(get_redis_queue),
    conn: asyncpg.Connection = Depends(get_db_conn),
):
    result = await job_service.create_job(
        conn,
        queue,
        tenant_id=str(request.tenant_id),
        job_type=request.job_type,
        payload=request.payload,
        idempotency_key=str(idempotency_key),
        priority=request.priority,
    )
    body = job_to_response(result.job, created=result.was_created)
    status_code = 201 if result.was_created else 200
    headers = {"Location": f"/jobs/{result.job_id}"} if result.was_created else None
    return api_response(body, status_code=status_code, headers=headers)


@router.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    response_model_exclude_none=True,
    responses=JOB_GET_RESPONSES,
)
async def get_job(
    job_id: Annotated[UUID, Path(description="Job UUID")],
    conn: asyncpg.Connection = Depends(get_db_conn),
):
    try:
        record = await job_service.get_job(conn, str(job_id))
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found") from None
    return job_to_response(record)


@router.get(
    "/jobs",
    response_model=List[JobResponse],
    response_model_exclude_none=True,
)
async def list_jobs(
    limit: int = Query(20, le=100),
    status: str | None = Query(None),
    conn: asyncpg.Connection = Depends(get_db_conn),
):
    rows = await job_service.list_jobs(conn, limit=limit, status=status)
    return [job_to_response(row) for row in rows]
