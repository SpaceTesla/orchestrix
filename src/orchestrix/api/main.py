from fastapi import FastAPI
from contextlib import asynccontextmanager

from orchestrix.api.routes import router
from orchestrix.db.pool import init_pool, close_pool
from orchestrix.queue.redis_client import init_redis_queue, close_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    print("[DB]: DB pool initialized")
    await init_redis_queue()
    print("[Redis]: Redis pool initialized")

    yield

    print("Shutting down...")
    await close_pool()
    await close_redis()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Orchestrix",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(router)

    return app


app = create_app()
