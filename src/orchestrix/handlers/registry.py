import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

Handler = Callable[[dict[str, Any]], Awaitable[None]]

_REGISTRY: dict[str, Handler] = {}


def register(job_type: str, handler: Handler) -> None:
    _REGISTRY[job_type] = handler


def get_handler(job_type: str) -> Handler | None:
    return _REGISTRY.get(job_type)


async def default_handler(payload: dict[str, Any]) -> None:
    await asyncio.sleep(10)


async def execute(job_type: str, payload: dict[str, Any]) -> None:
    handler = get_handler(job_type) or default_handler
    await handler(payload)
