from typing import Any

from orchestrix.api.schemas import ErrorResponse, JobResponse

_JOB_JSON = "application/json"

JOB_CREATED_EXAMPLE = {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "pending",
    "priority": "normal",
    "created": True,
}

JOB_REPLAYED_EXAMPLE = {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "pending",
    "created": False,
}

JOB_GET_EXAMPLE = {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "pending",
    "priority": "normal",
}

VALIDATION_ERROR_EXAMPLE = {
    "detail": [
        {
            "loc": ["header", "Idempotency-Key"],
            "msg": "Field required",
            "type": "missing",
        }
    ]
}

NOT_FOUND_EXAMPLE = {"detail": "Job not found"}


def _job_content(example: dict) -> dict:
    return {_JOB_JSON: {"example": example}}


JOB_POST_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "model": JobResponse,
        "description": "Existing job returned for duplicate idempotency key",
        "content": _job_content(JOB_REPLAYED_EXAMPLE),
    },
    201: {
        "model": JobResponse,
        "description": "New job created",
        "content": _job_content(JOB_CREATED_EXAMPLE),
    },
    422: {
        "description": "Request validation failed",
        "content": {_JOB_JSON: {"example": VALIDATION_ERROR_EXAMPLE}},
    },
}

JOB_GET_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "model": JobResponse,
        "description": "Job found",
        "content": _job_content(JOB_GET_EXAMPLE),
    },
    404: {
        "model": ErrorResponse,
        "description": "Job not found",
        "content": {_JOB_JSON: {"example": NOT_FOUND_EXAMPLE}},
    },
    422: {
        "description": "Invalid job ID",
        "content": {_JOB_JSON: {"example": VALIDATION_ERROR_EXAMPLE}},
    },
}
