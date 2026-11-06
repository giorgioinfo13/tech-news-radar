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
POSTGRES_SCHEMA = "tnr"


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
    """Use timestamptz on PostgreSQL and naive UTC on SQLite; expose aware UTC."""

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect):
        return dialect.type_descriptor(DateTime(timezone=dialect.name == "postgresql"))

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.utcoffset() is None:
            raise ValueError("Database timestamps must include a timezone")
        value = value.astimezone(UTC)
        return value if dialect.name == "postgresql" else value.replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def resolve_database_url(database_url: str | URL) -> URL:
    url = make_url(database_url)
    if url.drivername in {"postgres", "postgresql", "postgresql+psycopg"}:
        url = url.set(drivername="postgresql+psycopg")
        # Keep host, TLS and session configuration unambiguous. Do not let libpq
        # environment defaults or query overrides silently select another server.
        if (
            not url.host
            or not url.database
            or set(url.query) - {"sslmode", "sslrootcert", "connect_timeout"}
        ):
            raise ValueError("PostgreSQL requires a host/database and supported connection options")
        if url.port == 6543:
            raise ValueError("Use a direct connection or the session pooler on port 5432")
        sslmode = url.query.get("sslmode", "verify-full")
        local = url.host in {"localhost", "127.0.0.1", "::1"}
        if sslmode != "verify-full" and not (local and sslmode == "disable"):
            raise ValueError("PostgreSQL requires sslmode=verify-full (disable is local-only)")
        return url.update_query_dict({"sslmode": sslmode})
    if url.drivername not in {"sqlite", "sqlite+pysqlite"}:
        raise ValueError("Supported databases are SQLite and PostgreSQL with psycopg")
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
    if url.get_backend_name() == "postgresql":
        engine = create_engine(
            url,
            pool_size=3,
            max_overflow=0,
            pool_timeout=10,
            pool_pre_ping=True,
            pool_recycle=300,
            connect_args={"connect_timeout": int(url.query.get("connect_timeout", "10"))},
            hide_parameters=True,
        )
        event.listen(engine, "connect", _configure_postgres, insert=True)
        return engine

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


def _configure_postgres(connection, record: ConnectionPoolEntry) -> None:
    # Session pooler only: SET must survive transaction rollback and pool reuse.
    previous_autocommit = connection.autocommit
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SET SESSION search_path TO {POSTGRES_SCHEMA}")
            cursor.execute("SET SESSION TIME ZONE 'UTC'")
    finally:
        connection.autocommit = previous_autocommit
