# path: scripts/seed_jobs.py
#
# Inserts jobs through POST /jobs so each job is written to Postgres and
# enqueued on Redis (workers only consume the stream).

import asyncio
import os
import random
from uuid import UUID

import httpx

from orchestrix.config import settings
from orchestrix.db.pool import close_pool, init_pool

JOB_TYPES = ["test", "email", "report", "fail"]


def _api_base() -> str:
    return os.environ.get("ORCHESTRIX_API_URL", "http://127.0.0.1:8000").rstrip("/")


async def main() -> None:
    base = _api_base()
    pool = await init_pool()

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO tenants (name) VALUES ($1)
                ON CONFLICT (name) DO NOTHING
                """,
                settings.default_tenant_name,
            )
            tenant_id = await conn.fetchval(
                "SELECT id FROM tenants WHERE name = $1",
                settings.default_tenant_name,
            )
        assert tenant_id is not None

        tenant_uuid = tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))

        async with httpx.AsyncClient(base_url=base, timeout=30.0) as client:
            for i in range(10):
                job_type = random.choice(JOB_TYPES)
                response = await client.post(
                    "/jobs",
                    json={
                        "tenant_id": str(tenant_uuid),
                        "job_type": job_type,
                        "payload": {"job_number": i},
                    },
                )
                response.raise_for_status()
                data = response.json()
                print(f"POST /jobs -> {data.get('id')} ({data.get('status')})")

        print("Seeded 10 jobs via API (queued for workers)")

    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
