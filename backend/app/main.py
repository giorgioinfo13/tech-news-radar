"""Application factory with explicit configuration and no startup migrations."""

from asyncio import to_thread
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.api.articles import router as articles_router
from app.api.categories import router as categories_router
from app.api.collection import router as collection_router
from app.api.dependencies import get_current_user
from app.api.health import router as health_router
from app.api.invitations import router as invitations_router
from app.api.personal import router as personal_router
from app.api.sources import router as sources_router
from app.auth import SupabaseVerifier
from app.collection.scheduler import CollectionScheduler
from app.collection.service import Collector
from app.collection.trigger import CollectionTrigger
from app.config import Settings
from app.db import create_database_engine
from app.invitations import GoogleIdentityVerifier


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()
    if config.environment == "production" and config.migration_database_url is not None:
        raise ValueError("Do not give the web service operator database credentials")

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
        trigger = (
            CollectionTrigger(app.state.collector) if config.collection_trigger_secret else None
        )
        app.state.collection_trigger = trigger
        try:
            if scheduler is not None:
                scheduler.start()
            yield
        finally:
            if scheduler is not None:
                await to_thread(scheduler.stop)
            if trigger is not None:
                await to_thread(trigger.stop)
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
    app.state.auth_verifier = SupabaseVerifier(config.supabase_url) if config.supabase_url else None

    app.state.google_identity_verifier = (
        GoogleIdentityVerifier(config.supabase_url, config.supabase_publishable_key)
        if config.supabase_url
        else None
    )

    @app.middleware("http")
    async def private_responses(request, call_next):
        response = await call_next(request)
        # Applies to authenticated data and denials alike, including the external proxy.
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["CDN-Cache-Control"] = "no-store"
        response.headers["Vercel-CDN-Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    app.include_router(health_router, prefix="/api")
    app.include_router(collection_router, prefix="/api")
    for router in (
        categories_router,
        sources_router,
        articles_router,
        personal_router,
        invitations_router,
    ):
        app.include_router(router, prefix="/api", dependencies=[Depends(get_current_user)])
    return app
