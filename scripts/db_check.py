import asyncio

from orchestrix.db.pool import close_pool, init_pool


async def main() -> None:
    pool = await init_pool()

    try:
        async with pool.acquire() as conn:
            val = await conn.fetchval("SELECT 1")
            print("DB OK:", val)
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
