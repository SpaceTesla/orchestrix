def send_email(payload):
    print(f"[EMAIL] Sending email to {payload.get('to')}")


def generate_report(payload):
    print(f"[REPORT] Generating report for {payload.get('user_id')}")


def failing_job(payload):
    raise Exception("Intentional failure for testing")
