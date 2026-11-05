from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import URL, Engine

from app.db import create_database_engine


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
