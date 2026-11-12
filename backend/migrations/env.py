"""Use the application's database configuration for all migration commands."""

from contextlib import nullcontext

from alembic import context

from app import models  # noqa: F401 -- register all mapped tables
from app.config import Settings
from app.db import POSTGRES_SCHEMA, Base, UTCDateTime, create_database_engine, resolve_database_url

config = context.config
settings = Settings(_env_file=None) if config.get_main_option("sqlalchemy.url") else Settings()
database_url = (
    config.get_main_option("sqlalchemy.url")
    or settings.migration_database_url
    or settings.database_url
)
database_url = resolve_database_url(database_url)


def render_item(kind, obj, autogen_context):
    # Freeze the SQL storage type in revisions, not a dependency on application code.
    if kind == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def include_object(obj, name, kind, reflected, compare_to):
    # These PostgreSQL keys use exact hash exclusion constraints instead of B-trees.
    # Alembic does not autogenerate exclusion constraints; migration tests check them.
    if kind == "unique_constraint" and name in {
        "uq_sources_feed_url",
        "uq_articles_source_guid",
        "uq_articles_source_url",
    }:
        return False
    return True


if context.is_offline_mode():
    context.configure(
        url=database_url,
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_item=render_item,
    )
    with context.begin_transaction():
        context.execute(f"CREATE SCHEMA IF NOT EXISTS {POSTGRES_SCHEMA}")
        context.execute(f"SET LOCAL search_path TO {POSTGRES_SCHEMA}")
        context.run_migrations()
else:
    supplied_connection = config.attributes.get("connection")
    engine = None if supplied_connection is not None else create_database_engine(database_url)
    try:
        with nullcontext(supplied_connection) if engine is None else engine.begin() as connection:
            # Bootstrap the namespace before the unchanged initial revision.
            # All DDL and revision updates share this transaction.
            connection.exec_driver_sql(f"CREATE SCHEMA IF NOT EXISTS {POSTGRES_SCHEMA}")
            connection.dialect.default_schema_name = POSTGRES_SCHEMA
            context.configure(
                connection=connection,
                target_metadata=Base.metadata,
                render_item=render_item,
                include_object=include_object,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        if engine is not None:
            engine.dispose()
