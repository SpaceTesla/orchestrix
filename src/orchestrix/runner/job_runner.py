from datetime import datetime, timezone
from typing import List, Callable, Dict, Any, Optional

from orchestrix.models.job import Job, JobStatus


class JobRunner:
    def __init__(self):
        self.jobs: List[Job] = []
        self.handlers: Dict[str, Callable[[Dict[str, Any]], None]] = {}

    def register_handler(
        self, job_type: str, handler: Callable[[Dict[str, Any]], None]
    ) -> None:
        self.handlers[job_type] = handler

    def submit(self, job_type: str, payload: Dict[str, Any]) -> Job:
        job = Job(type=job_type, payload=payload)
        self.jobs.append(job)
        return job

    def run_next(self) -> Optional[Job]:
        # Pick first PENDING job
        job = next((j for j in self.jobs if j.status == JobStatus.PENDING), None)

        if not job:
            print("No pending jobs.")
            return None

        now = datetime.now(timezone.utc)

        # Mark as running BEFORE execution
        job.started_at = now
        job.status = JobStatus.RUNNING

        handler = self.handlers.get(job.type)

        if not handler:
            job.status = JobStatus.FAILED
            job.error_message = f"No handler for job type: {job.type}"
            job.completed_at = now
            return job

        try:
            handler(job.payload)

            job.status = JobStatus.SUCCESS
            job.completed_at = datetime.now(timezone.utc)

        except Exception as e:
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            job.completed_at = datetime.now(timezone.utc)

        return job

    def run_all(self) -> None:
        while any(job.status == JobStatus.PENDING for job in self.jobs):
            self.run_next()

    def list_jobs(self) -> List[Job]:
        return self.jobs
