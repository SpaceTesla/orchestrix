from orchestrix.runner.job_runner import JobRunner
from orchestrix.handlers.sample_handlers import (
    send_email,
    generate_report,
    failing_job,
)


def main():
    runner = JobRunner()

    # Register handlers
    runner.register_handler("email", send_email)
    runner.register_handler("report", generate_report)
    runner.register_handler("fail", failing_job)

    # Submit jobs
    runner.submit("email", {"to": "test@example.com"})
    runner.submit("report", {"user_id": 123})
    runner.submit("fail", {})
    runner.submit("email", {"to": "another@example.com"})
    runner.submit("unknown", {})  # to test missing handler

    # Run jobs
    runner.run_all()

    # Print results

    jobs = list(runner.list_jobs())

    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="Final Job States", header_style="bold")
        table.add_column("id", style="dim", no_wrap=True)
        table.add_column("type", style="cyan")
        table.add_column("status", style="bold")
        table.add_column("error", style="red")

        status_style = {
            "pending": "yellow",
            "running": "blue",
            "success": "green",
            "failed": "red",
        }

        for job in jobs:
            status = job.status.value
            style = status_style.get(status, "white")
            table.add_row(
                str(job.id),
                job.type,
                f"[{style}]{status}[/{style}]",
                job.error_message or "",
            )

        console.print(table)

    except Exception:
        print("\n--- Final Job States ---")

        print(" id | type | status | error")
        for job in jobs:
            print(f"{job.id} | {job.type} | {job.status.value} | {job.error_message}")


if __name__ == "__main__":
    main()
