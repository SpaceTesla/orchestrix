from orchestrix.db.pool import get_pool
from orchestrix.queue.redis_client import get_redis_queue_instance


def get_redis_queue():
    return get_redis_queue_instance()


async def get_db_conn():
    pool = get_pool()

    async with pool.acquire() as conn:
        yield conn
