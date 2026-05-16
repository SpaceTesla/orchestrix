import logging
import sys
from typing import Literal

import structlog
from structlog.types import Processor

LogFormat = Literal["json", "console"]

_configured = False


def configure_logging(
    *,
    log_level: str = "INFO",
    log_format: LogFormat = "console",
) -> None:
    global _configured
    if _configured:
        return

    level = getattr(logging, log_level.upper(), logging.INFO)
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if log_format == "json"
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    _configured = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


def bind_job_context(
    *,
    job_id: str,
    tenant_id: str,
    worker_id: str,
    attempt_count: int,
) -> None:
    structlog.contextvars.bind_contextvars(
        job_id=job_id,
        tenant_id=tenant_id,
        worker_id=worker_id,
        attempt_count=attempt_count,
    )


def clear_job_context() -> None:
    structlog.contextvars.clear_contextvars()


def reset_logging_for_tests() -> None:
    """Allow tests to reconfigure logging."""
    global _configured
    _configured = False
    structlog.reset_defaults()
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.WARNING)
