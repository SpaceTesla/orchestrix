from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field
from typing import Any, Dict, Literal

from orchestrix.queue.priority import JobPriority


class JobCreateRequest(BaseModel):
    tenant_id: UUID
    job_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    priority: JobPriority = JobPriority.NORMAL


class JobResponse(BaseModel):
    id: str
    status: str
    priority: str | None = None
    tenant_id: str | None = None
    attempt_count: int | None = None
    max_attempts: int | None = None
    scheduled_at: datetime | None = None
    error_message: str | None = None
    created: bool | None = None


class ErrorResponse(BaseModel):
    detail: str


class DependencyCheck(BaseModel):
    ok: bool
    error: str | None = None


class HealthResponse(BaseModel):
    status: Literal["healthy", "unhealthy"]
    postgres: DependencyCheck
    redis: DependencyCheck


class RootResponse(BaseModel):
    service: str
    version: str
    docs: str
    openapi: str
    health: str
