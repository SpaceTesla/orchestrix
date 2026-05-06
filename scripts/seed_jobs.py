# path: scripts/seed_jobs.py

import asyncio
import json
import random

from orchestrix.db.pool import close_pool, init_pool


JOB_TYPES = ["test", "email", "report", "fail"]


async def main():
    pool = await init_pool()

    try:
        async with pool.acquire() as conn:
            for i in range(10):
                job_type = random.choice(JOB_TYPES)

                await conn.execute(
                    """
                    INSERT INTO jobs (job_type, payload)
                    VALUES ($1, $2)
                    """,
                    job_type,
                    json.dumps({"job_number": i}),
                )

        print("Inserted 10 jobs ✅")

    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
