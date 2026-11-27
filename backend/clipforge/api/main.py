from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from clipforge.api.routers import jobs, projects, system, uploads
from clipforge.core.config import get_settings
from clipforge.core.db import dispose_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    s.staging_dir.mkdir(parents=True, exist_ok=True)
    yield
    from clipforge.workers.queue import ArqQueue, get_queue

    q = get_queue()
    if isinstance(q, ArqQueue):
        await q.close()
    await dispose_engine()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="CLIPFORGE AI API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Range", "Accept-Ranges", "Content-Length"],
    )
    for r in (system.router, uploads.router, projects.router, jobs.router):
        app.include_router(r, prefix="/api/v1")
    return app


app = create_app()
