from uuid import UUID

from pydantic import BaseModel, Field
from typing import Dict, Any, Literal


class JobCreateRequest(BaseModel):
    tenant_id: UUID
    job_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class JobResponse(BaseModel):
    id: str
    status: str


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
