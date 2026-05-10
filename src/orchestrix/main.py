import argparse
import asyncio


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orchestrix")
    sub = parser.add_subparsers(dest="command", required=True)

    api = sub.add_parser("api", help="Run the FastAPI server")
    api.add_argument("--host", default="0.0.0.0")
    api.add_argument("--port", type=int, default=8000)
    api.add_argument("--reload", action="store_true", default=False)
    api.add_argument("--log-level", default="info")

    sub.add_parser("worker", help="Run the worker loop")

    return parser


def _run_api(host: str, port: int, reload: bool, log_level: str) -> None:
    try:
        import uvicorn  # type: ignore
    except ModuleNotFoundError as e:
        raise SystemExit(
            "uvicorn is required to run the API. Install it and retry."
        ) from e

    uvicorn.run(
        "orchestrix.api.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level=log_level,
    )


def _run_worker() -> None:
    from orchestrix.worker.main import worker

    asyncio.run(worker())


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)

    if args.command == "api":
        _run_api(
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level=args.log_level,
        )
        return

    if args.command == "worker":
        _run_worker()
        return

    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
