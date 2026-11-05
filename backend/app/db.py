"""Database primitives. Importing this module does not open or migrate a database."""

from datetime import UTC, datetime
from pathlib import Path
from sqlite3 import Connection as SQLiteConnection

from sqlalchemy import URL, DateTime, Engine, MetaData, create_engine, event, make_url
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import ConnectionPoolEntry, StaticPool
from sqlalchemy.types import TypeDecorator

BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def utc_now() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Store naive UTC in SQL and expose aware UTC in Python; reject ambiguous input."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.utcoffset() is None:
            raise ValueError("Database timestamps must include a timezone")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None


def resolve_database_url(database_url: str | URL) -> URL:
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite":
        if url.query.get("uri") == "true":
            raise ValueError("SQLite URI mode is not supported; use a regular SQLite URL")
        if url.database and url.database != ":memory:":
            path = Path(url.database).expanduser()
            if not path.is_absolute():
                path = BACKEND_ROOT / path
            url = url.set(database=str(path.resolve()))
    return url


def _configure_sqlite(connection: SQLiteConnection, record: ConnectionPoolEntry) -> None:
    # SQLite ignores this PRAGMA inside a transaction, including PEP 249 mode.
    previous_autocommit = connection.autocommit
    connection.autocommit = True
    try:
        connection.execute("PRAGMA foreign_keys=ON").close()
    finally:
        connection.autocommit = previous_autocommit


def create_database_engine(database_url: str | URL) -> Engine:
    url = resolve_database_url(database_url)
    if url.get_backend_name() != "sqlite":
        return create_engine(url)

    if url.database and url.database != ":memory:":
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        pool_options = {}
    else:
        # Share one connection for an explicitly requested in-memory database.
        pool_options = {"poolclass": StaticPool}

    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "autocommit": False, "timeout": 5},
        **pool_options,
    )
    event.listen(engine, "connect", _configure_sqlite)
    return engine
