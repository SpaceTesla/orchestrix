import asyncio

from orchestrix.db.pool import create_pool


async def main() -> None:
    pool = await create_pool()

    try:
        async with pool.acquire() as conn:
            val = await conn.fetchval("SELECT 1")
            print("DB OK:", val)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
