import asyncio

from orchestrix.core.logging import get_logger

log = get_logger(__name__)


async def test_job(payload: dict) -> None:
    await asyncio.sleep(10)


async def send_email(payload):
    log.info("handler_send_email_start", to=payload.get("to"))
    await asyncio.sleep(2)
    log.info("handler_send_email_done", to=payload.get("to"))


async def generate_report(payload):
    log.info("handler_generate_report_start", user_id=payload.get("user_id"))
    await asyncio.sleep(3)
    log.info("handler_generate_report_done", user_id=payload.get("user_id"))


async def failing_job(payload):
    raise Exception("Intentional failure for testing")


async def long_running_job(payload):
    """Simulates a hung job for reaper / kill -9 testing."""
    duration = float(payload.get("duration_seconds", 600))
    log.info("handler_long_running_job_start", duration_seconds=duration)
    await asyncio.sleep(duration)
