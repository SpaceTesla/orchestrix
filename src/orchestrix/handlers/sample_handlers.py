import asyncio


async def send_email(payload):
    print(f"[EMAIL] Sending email to {payload.get('to')}")
    await asyncio.sleep(2)
    print(f"[EMAIL] Sent email to {payload.get('to')}")


async def generate_report(payload):
    print(f"[REPORT] Generating report for {payload.get('user_id')}")
    await asyncio.sleep(3)
    print(f"[REPORT] Generated report for {payload.get('user_id')}")


async def failing_job(payload):
    raise Exception("Intentional failure for testing")
