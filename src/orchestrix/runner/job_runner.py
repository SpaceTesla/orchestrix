# path: orchestrix/runner/job_runner.py

from datetime import datetime, timezone
from typing import List, Callable, Dict, Any, Optional, Awaitable, Annotated
from annotated_types import Ge
from uuid import UUID

import asyncio
from rich.console import Console

from orchestrix.models.job import Job, JobStatus, Timeout

MaxConcurrency = Annotated[int, Ge(1)]
DEFAULT_TIMEOUT = 10


class JobRunner:
    def __init__(self, debug: bool = False):
        self.jobs: List[Job] = []
        self.handlers: Dict[str, Callable[[Dict[str, Any]], Awaitable[None]]] = {}
        self.active_jobs = 0
        self.debug = debug
        self.console = Console()

    def _log(self, message: str, style: str = "white"):
        if self.debug:
            self.console.print(message, style=style)

    def register_handler(
        self, job_type: str, handler: Callable[[Dict[str, Any]], Awaitable[None]]
    ) -> None:
        self.handlers[job_type] = handler

    def submit(
        self,
        job_type: str,
        tenant_id: UUID,
        payload: Dict[str, Any],
        timeout: Optional[Timeout] = None,
    ) -> Job:
        job = Job(type=job_type, tenant_id=tenant_id, payload=payload, timeout=timeout)
        self.jobs.append(job)
        return job

    async def _run_job(self, job: Job) -> Job:
        # Prevent re-running non-pending jobs
        if job.status != JobStatus.PENDING:
            return job

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)

        handler = self.handlers.get(job.type)

        if not handler:
            job.status = JobStatus.FAILED
            job.error_message = f"No handler for job type: {job.type}"
            job.completed_at = datetime.now(timezone.utc)

            self._log(
                f"[{job.type}] NO HANDLER | id={job.id} tenant_id={job.tenant_id}",
                style="bold red",
            )
            return job

        # Count only valid execution attempts
        job.attempt_count += 1

        self.active_jobs += 1
        self._log(
            f"[{job.type}] START | id={job.id} tenant_id={job.tenant_id} "
            f"| attempt={job.attempt_count} | active={self.active_jobs}",
            style="cyan",
        )

        # Resolve timeout
        timeout = job.timeout if job.timeout is not None else DEFAULT_TIMEOUT
        if timeout < 0:
            raise ValueError("timeout must be >= 0")

        try:
            async with asyncio.timeout(timeout):
                await handler(job.payload)

            job.status = JobStatus.SUCCESS
            self._log(
                f"[{job.type}] SUCCESS | id={job.id} tenant_id={job.tenant_id}",
                style="green",
            )

        except asyncio.TimeoutError:
            job.status = JobStatus.FAILED
            job.error_message = f"timeout after {timeout}s"
            self._log(
                f"[{job.type}] TIMEOUT | id={job.id} tenant_id={job.tenant_id} "
                f"| timeout={timeout}s",
                style="yellow",
            )

        except Exception as e:
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            self._log(
                f"[{job.type}] FAILED | id={job.id} tenant_id={job.tenant_id} | error={e}",
                style="red",
            )

        finally:
            job.completed_at = datetime.now(timezone.utc)
            self.active_jobs = max(0, self.active_jobs - 1)
            self._log(
                f"[{job.type}] DONE | id={job.id} tenant_id={job.tenant_id} "
                f"| active={self.active_jobs}",
                style="dim",
            )

        return job

    async def _run_job_with_semaphore(self, job: Job, sem: asyncio.Semaphore):
        async with sem:
            return await self._run_job(job)

    async def run_next(self) -> Optional[Job]:
        job = next((j for j in self.jobs if j.status == JobStatus.PENDING), None)

        if not job:
            return None

        return await self._run_job(job)

    async def run_all(self, max_concurrency: MaxConcurrency = 5) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")

        sem = asyncio.Semaphore(max_concurrency)
        pending = [j for j in self.jobs if j.status == JobStatus.PENDING]

        if not pending:
            return

        async with asyncio.TaskGroup() as tg:
            for job in pending:
                tg.create_task(self._run_job_with_semaphore(job, sem))

    def list_jobs(self) -> List[Job]:
        return self.jobs
