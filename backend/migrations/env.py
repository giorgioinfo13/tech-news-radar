"""Use the application's database configuration for all migration commands."""

from alembic import context

from app import models  # noqa: F401 -- register all mapped tables
from app.config import Settings
from app.db import Base, UTCDateTime, create_database_engine, resolve_database_url

config = context.config
database_url = config.get_main_option("sqlalchemy.url") or Settings().database_url


def render_item(kind, obj, autogen_context):
    # Freeze the SQL storage type in revisions, not a dependency on application code.
    if kind == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime()"
    return False


if context.is_offline_mode():
    context.configure(
        url=resolve_database_url(database_url),
        target_metadata=Base.metadata,
        literal_binds=True,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_database_engine(database_url)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=Base.metadata,
                render_as_batch=engine.dialect.name == "sqlite",
                render_item=render_item,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
