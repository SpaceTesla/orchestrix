from orchestrix.handlers.registry import execute, register
from orchestrix.handlers.sample_handlers import (
    failing_job,
    generate_report,
    long_running_job,
    send_email,
    test_job,
)


def register_handlers() -> None:
    register("test", test_job)
    register("send_email", send_email)
    register("generate_report", generate_report)
    register("failing_job", failing_job)
    register("long_running_job", long_running_job)


__all__ = ["execute", "register", "register_handlers"]
