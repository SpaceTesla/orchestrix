from datetime import datetime, timezone

from orchestrix.api.responses import api_response
from orchestrix.api.schemas import JobResponse


def test_api_response_serializes_datetime() -> None:
    response = api_response(
        JobResponse(
            id="550e8400-e29b-41d4-a716-446655440000",
            status="pending",
            scheduled_at=datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc),
            created=True,
        ),
        status_code=201,
    )

    assert response.status_code == 201
    body = response.body.decode()
    assert "2026-05-16T12:00:00" in body
