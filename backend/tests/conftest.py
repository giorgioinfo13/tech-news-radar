from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import URL, Engine

from app.config import Settings
from app.db import create_database_engine
from app.main import create_app


@pytest.fixture
def migration_config(tmp_path: Path) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    # Exercise config escaping as well as paths that contain spaces.
    url = URL.create("sqlite", database=str(tmp_path / "news 100%.db"))
    config.set_main_option("sqlalchemy.url", url.render_as_string().replace("%", "%%"))
    return config


@pytest.fixture
def database(migration_config: Config) -> Iterator[Engine]:
    # All model tests run against the real migration, never metadata.create_all().
    command.upgrade(migration_config, "head")
    engine = create_database_engine(migration_config.get_main_option("sqlalchemy.url"))
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client(database: Engine) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        _env_file=None, database_url=database.url.render_as_string(), scheduler_enabled=False
    )
    app = create_app(settings)
    # ASGITransport does not start lifespan automatically. Exercise production setup.
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
