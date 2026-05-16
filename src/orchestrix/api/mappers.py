from datetime import datetime, timezone
from typing import Any, Mapping

from orchestrix.api.schemas import JobResponse


def _optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    return None


def job_to_response(
    record: Mapping[str, Any],
    *,
    created: bool | None = None,
) -> JobResponse:
    priority = record.get("priority")
    tenant_id = record.get("tenant_id")

    return JobResponse(
        id=str(record["id"]),
        status=str(record["status"]),
        priority=str(priority) if priority is not None else None,
        tenant_id=str(tenant_id) if tenant_id is not None else None,
        attempt_count=record.get("attempt_count"),
        max_attempts=record.get("max_attempts"),
        scheduled_at=_optional_datetime(record.get("scheduled_at")),
        error_message=record.get("error_message"),
        created=created,
    )
