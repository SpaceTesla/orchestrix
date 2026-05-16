from datetime import datetime, timezone
from uuid import UUID

from orchestrix.api.mappers import job_to_response


def test_job_to_response_maps_phase7_fields() -> None:
    job_id = UUID("550e8400-e29b-41d4-a716-446655440000")
    tenant_id = UUID("660e8400-e29b-41d4-a716-446655440001")
    scheduled_at = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)

    response = job_to_response(
        {
            "id": job_id,
            "status": "pending",
            "priority": "high",
            "tenant_id": tenant_id,
            "attempt_count": 0,
            "max_attempts": 3,
            "scheduled_at": scheduled_at,
            "error_message": None,
        },
        created=True,
    )

    assert response.id == str(job_id)
    assert response.status == "pending"
    assert response.priority == "high"
    assert response.tenant_id == str(tenant_id)
    assert response.attempt_count == 0
    assert response.max_attempts == 3
    assert response.scheduled_at == scheduled_at
    assert response.error_message is None
    assert response.created is True
