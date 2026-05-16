import redis.asyncio as redis
from typing import List, Tuple

from orchestrix.config import settings
from orchestrix.core.logging import get_logger
from orchestrix.queue.priority import (
    ALL_JOB_STREAMS,
    POLL_SEQUENCE,
    JobPriority,
    stream_for_priority,
)

log = get_logger(__name__)

_queue = None


class RedisQueue:
    def __init__(
        self,
        url: str,
        group_name: str = "workers",
    ):
        self.redis = redis.from_url(url, decode_responses=True)
        self.group = group_name
        self._poll_index = 0

    def next_poll_stream(self) -> str:
        stream = POLL_SEQUENCE[self._poll_index]
        self._poll_index = (self._poll_index + 1) % len(POLL_SEQUENCE)
        return stream

    async def create_groups(self) -> None:
        for stream in ALL_JOB_STREAMS:
            await self._create_group(stream)

    async def _create_group(self, stream: str) -> None:
        try:
            await self.redis.xgroup_create(
                name=stream,
                groupname=self.group,
                id="$",
                mkstream=True,
            )
        except redis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                return
            log.error(
                "redis_create_group_failed",
                exc_info=True,
                stream=stream,
                group=self.group,
            )
            raise

    async def enqueue(self, job_id: str, priority: JobPriority | str) -> str:
        stream = stream_for_priority(priority)
        try:
            message_id = await self.redis.xadd(
                stream,
                {"job_id": job_id},
            )
        except Exception:
            log.error(
                "redis_enqueue_failed",
                exc_info=True,
                job_id=job_id,
                stream=stream,
                priority=str(priority),
            )
            raise
        return message_id

    async def read(
        self,
        stream: str,
        consumer_name: str,
        count: int = 1,
        block: int = 2000,
    ) -> List[Tuple[str, dict]]:
        try:
            response = await self.redis.xreadgroup(
                groupname=self.group,
                consumername=consumer_name,
                streams={stream: ">"},
                count=count,
                block=block,
            )
        except Exception:
            log.error(
                "redis_read_failed",
                exc_info=True,
                stream=stream,
                consumer_name=consumer_name,
            )
            raise

        if not response:
            return []

        messages = []

        for _stream_name, entries in response:
            for message_id, data in entries:
                messages.append((message_id, data))

        return messages

    async def ack(self, stream: str, message_id: str) -> None:
        try:
            await self.redis.xack(stream, self.group, message_id)
        except Exception:
            log.error(
                "redis_ack_failed",
                exc_info=True,
                stream=stream,
                message_id=message_id,
            )
            raise

    async def autoclaim(
        self,
        stream: str,
        consumer_name: str,
        min_idle_time: int = 60000,
        count: int = 10,
    ):
        try:
            result = await self.redis.xautoclaim(
                name=stream,
                groupname=self.group,
                consumername=consumer_name,
                min_idle_time=min_idle_time,
                start_id="0-0",
                count=count,
            )
        except Exception:
            log.error(
                "redis_autoclaim_failed",
                exc_info=True,
                stream=stream,
                consumer_name=consumer_name,
            )
            raise

        messages = result[1]
        return messages

    async def close(self):
        await self.redis.aclose()


async def init_redis_queue() -> RedisQueue:
    global _queue

    if _queue is None:
        try:
            _queue = RedisQueue(
                url=settings.redis_url,
            )
            await _queue.create_groups()
        except Exception:
            log.critical("redis_queue_init_failed", exc_info=True)
            _queue = None
            raise

    return _queue


def get_redis_queue_instance() -> RedisQueue:
    if _queue is None:
        raise RuntimeError("Redis queue not initialized")

    return _queue


async def close_redis():
    global _queue

    if _queue:
        await _queue.close()

    _queue = None
