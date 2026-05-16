from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, Annotated
from annotated_types import Ge
from datetime import datetime, timedelta, timezone
import uuid


class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    DEAD = "dead"


Timeout = Annotated[int, Ge(0)]


@dataclass
class Job:
    type: str
    tenant_id: uuid.UUID
    payload: Dict[str, Any] = field(default_factory=dict)

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    status: JobStatus = JobStatus.PENDING

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    error_message: Optional[str] = None

    timeout: Optional[Timeout] = None
    attempt_count: int = 0
    max_attempts: int = 3
    scheduled_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return (
            f"<Job id={self.id} tenant_id={self.tenant_id} "
            f"type={self.type} status={self.status.value}>"
        )
