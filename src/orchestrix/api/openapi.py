from typing import Any

from orchestrix.api.schemas import ErrorResponse, JobResponse

_JOB_JSON = "application/json"

_JOB_DETAIL = {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "pending",
    "priority": "normal",
    "tenant_id": "660e8400-e29b-41d4-a716-446655440001",
    "attempt_count": 0,
    "max_attempts": 3,
    "scheduled_at": "2026-05-16T12:00:00+00:00",
    "error_message": None,
}

JOB_CREATED_EXAMPLE = {**_JOB_DETAIL, "created": True}

JOB_REPLAYED_EXAMPLE = {**_JOB_DETAIL, "created": False}

JOB_GET_EXAMPLE = {k: v for k, v in _JOB_DETAIL.items() if k != "created"}

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
