import redis.asyncio as redis
from typing import List, Tuple

from orchestrix.config import settings


_queue = None


class RedisQueue:
    def __init__(
        self,
        url: str,
        stream_name: str = "jobs:queue",
        group_name: str = "workers",
    ):
        self.redis = redis.from_url(url, decode_responses=True)
        self.stream = stream_name
        self.group = group_name

    async def create_group(self) -> None:
        try:
            await self.redis.xgroup_create(
                name=self.stream,
                groupname=self.group,
                id="$",
                mkstream=True,
            )
        except redis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                # group already exists → fine
                return
            raise

    async def enqueue(self, job_id: str) -> str:
        message_id = await self.redis.xadd(
            self.stream,
            {"job_id": job_id},
        )
        return message_id

    async def read(
        self,
        consumer_name: str,
        count: int = 1,
        block: int = 2000,
    ) -> List[Tuple[str, dict]]:
        response = await self.redis.xreadgroup(
            groupname=self.group,
            consumername=consumer_name,
            streams={self.stream: ">"},
            count=count,
            block=block,
        )

        if not response:
            return []

        messages = []

        for stream, entries in response:
            for message_id, data in entries:
                messages.append((message_id, data))

        return messages

    async def ack(self, message_id: str) -> None:
        await self.redis.xack(self.stream, self.group, message_id)

    async def autoclaim(
        self,
        consumer_name: str,
        min_idle_time: int = 60000,  # ms
        count: int = 10,
    ):
        # redis-py may return (next_id, messages) or (next_id, messages, deleted_ids)
        result = await self.redis.xautoclaim(
            name=self.stream,
            groupname=self.group,
            consumername=consumer_name,
            min_idle_time=min_idle_time,
            start_id="0-0",
            count=count,
        )

        messages = result[1]
        return messages

    async def close(self):
        self.redis.close()


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
        _queue.close()

    _queue = None
