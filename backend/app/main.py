"""Application factory for local development and isolated tests."""

from asyncio import to_thread
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.api.articles import router as articles_router
from app.api.categories import router as categories_router
from app.api.dependencies import get_current_user
from app.api.health import router as health_router
from app.api.personal import router as personal_router
from app.api.sources import router as sources_router
from app.collection.scheduler import CollectionScheduler
from app.collection.service import Collector
from app.config import Settings
from app.db import create_database_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_database_engine(config.database_url)
        app.state.database_engine = engine
        app.state.collector = Collector(engine, config)
        scheduler = (
            CollectionScheduler(app.state.collector, config.scheduler_poll_seconds)
            if config.scheduler_enabled
            else None
        )
        app.state.scheduler = scheduler
        try:
            if scheduler is not None:
                scheduler.start()
            yield
        finally:
            if scheduler is not None:
                await to_thread(scheduler.stop)
            engine.dispose()

    app = FastAPI(
        title=config.app_name,
        version="0.1.0",
        docs_url="/docs" if config.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if config.docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = config
    app.include_router(health_router, prefix="/api")
    for router in (categories_router, sources_router, articles_router, personal_router):
        app.include_router(router, prefix="/api", dependencies=[Depends(get_current_user)])
    return app
