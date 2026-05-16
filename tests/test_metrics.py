from prometheus_client import REGISTRY

from orchestrix.core.metrics import (
    observe_job_attempts,
    observe_job_duration,
    record_job_completed,
    record_job_submitted,
    record_rate_limit_rejection,
    set_queue_depth,
    worker_active_jobs_dec,
    worker_active_jobs_inc,
)


def test_record_job_submitted() -> None:
    record_job_submitted(tenant_id="tenant-submit", priority="high")
    value = REGISTRY.get_sample_value(
        "jobs_submitted_total",
        labels={"tenant_id": "tenant-submit", "priority": "high"},
    )
    assert value == 1.0


def test_record_job_completed() -> None:
    record_job_completed(
        tenant_id="tenant-done",
        job_type="send_email",
        status="success",
    )
    value = REGISTRY.get_sample_value(
        "jobs_completed_total",
        labels={
            "tenant_id": "tenant-done",
            "job_type": "send_email",
            "status": "success",
        },
    )
    assert value == 1.0


def test_worker_active_jobs_gauge() -> None:
    worker_active_jobs_inc(worker_id="worker-gauge-test")
    worker_active_jobs_inc(worker_id="worker-gauge-test")
    worker_active_jobs_dec(worker_id="worker-gauge-test")
    value = REGISTRY.get_sample_value(
        "worker_active_jobs",
        labels={"worker_id": "worker-gauge-test"},
    )
    assert value == 1.0


def test_rate_limit_and_queue_depth() -> None:
    record_rate_limit_rejection(tenant_id="tenant-rl")
    set_queue_depth(priority="normal", depth=42)
    observe_job_duration(job_type="report", duration_seconds=0.25)
    observe_job_attempts(3)

    assert (
        REGISTRY.get_sample_value(
            "rate_limit_rejections_total",
            labels={"tenant_id": "tenant-rl"},
        )
        == 1.0
    )
    assert (
        REGISTRY.get_sample_value(
            "queue_depth",
            labels={"priority": "normal"},
        )
        == 42.0
    )
    assert (
        REGISTRY.get_sample_value(
            "job_duration_seconds_count",
            labels={"job_type": "report"},
        )
        == 1.0
    )
    assert REGISTRY.get_sample_value("job_attempt_count_count") == 1.0
