import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.pool import NullPool

from app.config import Settings
from app.db import create_database_engine, resolve_database_url
from app.main import create_app
from app.models import LOCAL_OWNER_ID


def pytest_addoption(parser):
    parser.addoption(
        "--postgres", action="store_true", help="Use isolated local PostgreSQL databases"
    )


@pytest.fixture
def migration_config(tmp_path: Path, request) -> Iterator[Config]:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    # Exercise config escaping as well as paths that contain spaces.
    url = URL.create("sqlite", database=str(tmp_path / "news 100%.db"))
    admin = None
    if request.config.getoption("--postgres"):
        value = os.environ.get("TNR_TEST_POSTGRES_URL")
        if not value:
            pytest.fail("--postgres requires TNR_TEST_POSTGRES_URL (a disposable local server)")
        url = resolve_database_url(value)
        if url.get_backend_name() != "postgresql" or url.host not in {"127.0.0.1", "::1"}:
            pytest.fail(
                "PostgreSQL tests require a literal loopback host; remote databases forbidden"
            )
        admin = create_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
        # Never drop or migrate the supplied database. Each test owns a fresh database.
        name = f"tnr_test_{uuid4().hex}"
        with admin.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{name}" TEMPLATE template0')
        url = url.set(database=name)
    config.set_main_option(
        "sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%")
    )
    try:
        yield config
    finally:
        if admin is not None:
            try:
                with admin.connect() as connection:
                    connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
            finally:
                admin.dispose()


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
        _env_file=None,
        database_url=database.url.render_as_string(hide_password=False),
        local_user_id=LOCAL_OWNER_ID,
        scheduler_enabled=False,
    )
    app = create_app(settings)
    # ASGITransport does not start lifespan automatically. Exercise production setup.
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client


@pytest.fixture(autouse=True)
def isolated_settings_and_http(monkeypatch):
    """Tests never load personal dotenv files or send real HTTP, even by accident."""
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for name in list(os.environ):
        if name.startswith("TNR_") and name != "TNR_TEST_POSTGRES_URL":
            monkeypatch.delenv(name)

    def denied(*args, **kwargs):
        raise AssertionError("Real HTTP is forbidden in tests; supply a simulated transport")

    async def denied_async(*args, **kwargs):
        denied()

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", denied)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", denied_async)
