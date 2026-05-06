import asyncio
from pathlib import Path

from orchestrix.db.pool import close_pool, init_pool


async def main():
    pool = await init_pool()

    try:
        async with pool.acquire() as conn:
            sql = Path("src/orchestrix/db/migrations/schema.sql").read_text()
            await conn.execute(sql)
            print("Schema created")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
