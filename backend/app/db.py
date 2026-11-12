"""Database primitives. Importing this module does not open or migrate a database."""

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import URL, DateTime, Engine, MetaData, create_engine, event, make_url, text
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.pool import ConnectionPoolEntry
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
    """Store timezone-aware UTC values in PostgreSQL timestamptz columns."""

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect):
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.utcoffset() is None:
            raise ValueError("Database timestamps must include a timezone")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def resolve_database_url(database_url: str | URL) -> URL:
    url = make_url(database_url)
    if url.drivername not in {"postgres", "postgresql", "postgresql+psycopg"}:
        raise ValueError("PostgreSQL with psycopg is the only supported database")
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


def create_database_engine(database_url: str | URL) -> Engine:
    url = resolve_database_url(database_url)
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


def lock_access_decisions(session: Session) -> None:
    """Serialize proposal decisions and operator access changes until commit/rollback.

    Acquire before reading mutable authorization state. Callers own the transaction;
    this helper must not discard their pending changes or commit on their behalf.
    """
    with session.no_autoflush:
        session.execute(text("SELECT pg_advisory_xact_lock(746674, 6)"))


def insert_once(session: Session, model: type[Base], values: dict) -> None:
    """Atomically insert a personal state row; repeated requests are idempotent."""
    from sqlalchemy.dialects.postgresql import insert

    session.execute(
        insert(model)
        .values(**values)
        .on_conflict_do_nothing(index_elements=list(model.__table__.primary_key.columns))
    )
