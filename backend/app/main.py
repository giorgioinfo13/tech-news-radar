"""Application factory for local development and isolated tests."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.articles import router as articles_router
from app.api.categories import router as categories_router
from app.api.health import router as health_router
from app.api.sources import router as sources_router
from app.config import Settings
from app.db import create_database_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_database_engine(config.database_url)
        app.state.database_engine = engine
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(
        title=config.app_name,
        version="0.1.0",
        docs_url="/docs" if config.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if config.docs_enabled else None,
        lifespan=lifespan,
    )
    app.include_router(health_router, prefix="/api")
    app.include_router(categories_router, prefix="/api")
    app.include_router(sources_router, prefix="/api")
    app.include_router(articles_router, prefix="/api")
    return app
