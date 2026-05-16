import json

import pytest

from orchestrix.core.logging import (
    bind_job_context,
    clear_job_context,
    configure_logging,
    get_logger,
    reset_logging_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_logging() -> None:
    reset_logging_for_tests()
    yield
    reset_logging_for_tests()


def test_bind_job_context_emits_json_fields(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(log_level="DEBUG", log_format="json")
    clear_job_context()
    bind_job_context(
        job_id="job-1",
        tenant_id="tenant-1",
        worker_id="worker-1",
        attempt_count=2,
    )
    get_logger("test").info("test_event", extra_field="ok")
    clear_job_context()

    line = capsys.readouterr().out.strip().splitlines()[-1]
    event = json.loads(line)

    assert event["event"] == "test_event"
    assert event["job_id"] == "job-1"
    assert event["tenant_id"] == "tenant-1"
    assert event["worker_id"] == "worker-1"
    assert event["attempt_count"] == 2
    assert event["extra_field"] == "ok"


def test_clear_job_context_removes_bound_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(log_level="DEBUG", log_format="json")
    bind_job_context(
        job_id="job-1",
        tenant_id="tenant-1",
        worker_id="worker-1",
        attempt_count=0,
    )
    clear_job_context()
    get_logger("test").info("after_clear")

    line = capsys.readouterr().out.strip().splitlines()[-1]
    event = json.loads(line)

    assert event["event"] == "after_clear"
    assert "job_id" not in event


def test_configure_logging_is_idempotent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(log_level="DEBUG", log_format="json")
    configure_logging(log_level="INFO", log_format="console")
    get_logger("test").info("once")

    lines = [ln for ln in capsys.readouterr().out.strip().splitlines() if ln]
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["event"] == "once"
