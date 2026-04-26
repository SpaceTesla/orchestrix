import asyncpg

from orchestrix.config import settings


async def create_pool():
    return await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=2,
        max_size=10,
    )
