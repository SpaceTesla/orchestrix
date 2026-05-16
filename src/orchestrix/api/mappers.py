from typing import Any, Mapping

from orchestrix.api.schemas import JobResponse


def job_to_response(
    record: Mapping[str, Any],
    *,
    created: bool | None = None,
) -> JobResponse:
    priority = record.get("priority")
    return JobResponse(
        id=str(record["id"]),
        status=str(record["status"]),
        priority=str(priority) if priority is not None else None,
        created=created,
    )
