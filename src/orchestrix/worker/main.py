# path: src/orchestrix/worker/main.py

import asyncio
import socket
import os
import signal

from orchestrix.db.pool import create_pool
from orchestrix.db.queries import fetch_next_job, transition_status


WORKER_ID = f"{socket.gethostname()}-{os.getpid()}"


async def handle_job(job):
    print(f"[START] Job {job['id']} | type={job['job_type']}")

    await asyncio.sleep(1)  # simulate work

    if job["job_type"] == "fail":
        raise Exception("Simulated failure")

    print(f"[DONE] Job {job['id']}")


async def worker_loop():
    pool = await create_pool()
    print(f"[WORKER STARTED] id={WORKER_ID}")

    shutdown_event = asyncio.Event()
    idle_count = 0

    # --- graceful shutdown ---
    def handle_shutdown():
        print("[SHUTDOWN SIGNAL RECEIVED]")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, handle_shutdown)
        loop.add_signal_handler(signal.SIGTERM, handle_shutdown)
    except NotImplementedError:
        # Windows fallback (signals behave differently)
        pass

    try:
        while not shutdown_event.is_set():
            # 1. Fetch job
            async with pool.acquire() as conn:
                job = await fetch_next_job(conn)

            if not job:
                idle_count += 1
                if idle_count % 5 == 0:
                    print("[IDLE] waiting for jobs...")
                try:
                    # wake early if shutdown signal arrives
                    await asyncio.wait_for(shutdown_event.wait(), timeout=1)
                except asyncio.TimeoutError:
                    pass
                continue

            idle_count = 0
            job_id = str(job["id"])

            # 2. Try to claim job
            async with pool.acquire() as conn:
                claimed = await transition_status(
                    conn,
                    job_id=job_id,
                    old_status="pending",
                    new_status="running",
                    worker_id=WORKER_ID,
                )

            if not claimed:
                print(f"[RACE LOST] Job {job_id}")
                await asyncio.sleep(0.1)  # prevent busy spin
                continue

            print(f"[CLAIMED] Job {job_id}")

            # 3. Execute WITHOUT holding DB connection
            try:
                await handle_job(job)

                async with pool.acquire() as conn:
                    await transition_status(
                        conn,
                        job_id=job_id,
                        old_status="running",
                        new_status="success",
                        worker_id=WORKER_ID,
                    )

                print(f"[SUCCESS] Job {job_id}")

            except Exception as e:
                print(f"[FAILED] Job {job_id} | error={e}")

                async with pool.acquire() as conn:
                    await transition_status(
                        conn,
                        job_id=job_id,
                        old_status="running",
                        new_status="failed",
                        worker_id=WORKER_ID,
                        error_message=str(e),
                    )

    except asyncio.CancelledError:
        print("[CANCELLED] Worker shutting down cleanly")

    finally:
        print("[SHUTDOWN] Closing DB pool")
        await pool.close()
