from typing import Any, Mapping

from orchestrix.api.schemas import JobResponse


def job_to_response(
    record: Mapping[str, Any],
    *,
    created: bool | None = None,
) -> JobResponse:
    return JobResponse(
        id=str(record["id"]),
        status=str(record["status"]),
        created=created,
    )
