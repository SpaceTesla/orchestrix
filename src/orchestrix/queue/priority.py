from enum import Enum


class JobPriority(str, Enum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


PRIORITY_TO_STREAM: dict[JobPriority, str] = {
    JobPriority.HIGH: "jobs:high",
    JobPriority.NORMAL: "jobs:normal",
    JobPriority.LOW: "jobs:low",
}

ALL_JOB_STREAMS: tuple[str, ...] = (
    "jobs:high",
    "jobs:normal",
    "jobs:low",
)

# 5 high : 3 normal : 1 low per cycle
POLL_SEQUENCE: tuple[str, ...] = (
    "jobs:high",
    "jobs:high",
    "jobs:high",
    "jobs:high",
    "jobs:high",
    "jobs:normal",
    "jobs:normal",
    "jobs:normal",
    "jobs:low",
)


def stream_for_priority(priority: JobPriority | str) -> str:
    if isinstance(priority, str):
        priority = JobPriority(priority)
    return PRIORITY_TO_STREAM[priority]
