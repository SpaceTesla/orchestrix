from pydantic import BaseModel, Field
from typing import Dict, Any


class JobCreateRequest(BaseModel):
    job_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class JobResponse(BaseModel):
    id: str
    status: str
