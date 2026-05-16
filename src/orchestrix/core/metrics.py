from prometheus_client import Counter, Gauge, Histogram

from orchestrix.queue.priority import ALL_JOB_STREAMS, JobPriority

JOB_DURATION_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)
JOB_ATTEMPT_BUCKETS = (1, 2, 3, 4, 5)

STREAM_TO_PRIORITY: dict[str, str] = {
    "jobs:high": JobPriority.HIGH.value,
    "jobs:normal": JobPriority.NORMAL.value,
    "jobs:low": JobPriority.LOW.value,
}

jobs_submitted_total = Counter(
    "jobs_submitted_total",
    "Total jobs submitted",
    ["tenant_id", "priority"],
)

jobs_completed_total = Counter(
    "jobs_completed_total",
    "Total jobs completed",
    ["tenant_id", "job_type", "status"],
)

job_duration_seconds = Histogram(
    "job_duration_seconds",
    "Handler execution time",
    ["job_type"],
    buckets=JOB_DURATION_BUCKETS,
)

rate_limit_rejections_total = Counter(
    "rate_limit_rejections_total",
    "Rate limit hits",
    ["tenant_id"],
)

worker_active_jobs = Gauge(
    "worker_active_jobs",
    "Currently executing jobs",
    ["worker_id"],
)

queue_depth = Gauge(
    "queue_depth",
    "Jobs in queue",
    ["priority"],
)

job_attempt_count = Histogram(
    "job_attempt_count",
    "Attempts per job",
    buckets=JOB_ATTEMPT_BUCKETS,
)


def record_job_submitted(*, tenant_id: str, priority: str) -> None:
    jobs_submitted_total.labels(tenant_id=tenant_id, priority=priority).inc()


def record_job_completed(
    *, tenant_id: str, job_type: str, status: str
) -> None:
    jobs_completed_total.labels(
        tenant_id=tenant_id,
        job_type=job_type,
        status=status,
    ).inc()


def observe_job_duration(*, job_type: str, duration_seconds: float) -> None:
    job_duration_seconds.labels(job_type=job_type).observe(duration_seconds)


def observe_job_attempts(attempt_count: int) -> None:
    job_attempt_count.observe(float(attempt_count))


def record_rate_limit_rejection(*, tenant_id: str) -> None:
    rate_limit_rejections_total.labels(tenant_id=tenant_id).inc()


def worker_active_jobs_inc(*, worker_id: str) -> None:
    worker_active_jobs.labels(worker_id=worker_id).inc()


def worker_active_jobs_dec(*, worker_id: str) -> None:
    worker_active_jobs.labels(worker_id=worker_id).dec()


def set_queue_depth(*, priority: str, depth: int) -> None:
    queue_depth.labels(priority=priority).set(depth)


async def refresh_queue_depth(queue) -> None:
    """Set queue_depth gauge from Redis stream lengths (XLEN per priority stream)."""
    for stream in ALL_JOB_STREAMS:
        priority = STREAM_TO_PRIORITY[stream]
        depth = await queue.redis.xlen(stream)
        set_queue_depth(priority=priority, depth=depth)
