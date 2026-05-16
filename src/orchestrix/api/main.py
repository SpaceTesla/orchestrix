from contextlib import asynccontextmanager

from fastapi import FastAPI

from orchestrix.api.middleware import RequestLoggingMiddleware
from orchestrix.api.routes import router
from orchestrix.config import settings
from orchestrix.core.logging import configure_logging, get_logger
from orchestrix.db.pool import close_pool, init_pool
from orchestrix.queue.redis_client import close_redis, init_redis_queue

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(
        log_level=settings.log_level,
        log_format=settings.log_format,
    )
    await init_pool()
    log.info("db_pool_initialized")
    await init_redis_queue()
    log.info("redis_queue_initialized")

    yield

    log.info("api_shutting_down")
    await close_pool()
    await close_redis()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Orchestrix",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(RequestLoggingMiddleware)
    app.include_router(router)

    return app


app = create_app()
