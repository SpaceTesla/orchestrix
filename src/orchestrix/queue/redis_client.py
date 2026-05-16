import redis.asyncio as redis
from typing import List, Tuple

from orchestrix.config import settings
from orchestrix.queue.priority import (
    ALL_JOB_STREAMS,
    POLL_SEQUENCE,
    JobPriority,
    stream_for_priority,
)


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
            raise

    async def enqueue(self, job_id: str, priority: JobPriority | str) -> str:
        stream = stream_for_priority(priority)
        message_id = await self.redis.xadd(
            stream,
            {"job_id": job_id},
        )
        return message_id

    async def read(
        self,
        stream: str,
        consumer_name: str,
        count: int = 1,
        block: int = 2000,
    ) -> List[Tuple[str, dict]]:
        response = await self.redis.xreadgroup(
            groupname=self.group,
            consumername=consumer_name,
            streams={stream: ">"},
            count=count,
            block=block,
        )

        if not response:
            return []

        messages = []

        for _stream_name, entries in response:
            for message_id, data in entries:
                messages.append((message_id, data))

        return messages

    async def ack(self, stream: str, message_id: str) -> None:
        await self.redis.xack(stream, self.group, message_id)

    async def autoclaim(
        self,
        stream: str,
        consumer_name: str,
        min_idle_time: int = 60000,
        count: int = 10,
    ):
        result = await self.redis.xautoclaim(
            name=stream,
            groupname=self.group,
            consumername=consumer_name,
            min_idle_time=min_idle_time,
            start_id="0-0",
            count=count,
        )

        messages = result[1]
        return messages

    async def close(self):
        await self.redis.aclose()


async def init_redis_queue() -> RedisQueue:
    global _queue

    if _queue is None:
        _queue = RedisQueue(
            url=settings.redis_url,
        )

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
