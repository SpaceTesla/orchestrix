import asyncpg
from orchestrix.config import settings

_pool: asyncpg.Pool | None = None


async def init_pool() -> asyncpg.Pool:
    global _pool

    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )

    return _pool


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialized")
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
