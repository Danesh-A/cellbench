"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cellbench_api import __version__
from cellbench_api.config import get_settings
from cellbench_api.routers import auth, challenges, datasets, models, submissions
from cellbench_api.storage import ensure_bucket

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Startup / shutdown hooks."""
    settings = get_settings()
    log.info("startup", env=settings.env, version=__version__)
    try:
        ensure_bucket()
    except Exception as e:  # pragma: no cover — best-effort
        log.warning("bucket_init_failed", error=str(e))
    yield
    log.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="CellBench API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix="/v1/auth", tags=["auth"])
    app.include_router(datasets.router, prefix="/v1/datasets", tags=["datasets"])
    app.include_router(challenges.router, prefix="/v1/challenges", tags=["challenges"])
    app.include_router(submissions.router, prefix="/v1/submissions", tags=["submissions"])
    app.include_router(models.router, prefix="/v1/models", tags=["models"])

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
