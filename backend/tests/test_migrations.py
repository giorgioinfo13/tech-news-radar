from io import StringIO
from pathlib import Path

from alembic import command
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.db import resolve_database_url
from app.models import Category, Source


def test_initial_migration_matches_models_and_seeds_categories(database, migration_config):
    assert set(inspect(database).get_table_names()) == {
        "alembic_version",
        "categories",
        "sources",
        "articles",
        "collection_runs",
        "app_users",
        "subscriptions",
        "article_read_states",
    }
    with Session(database) as session:
        categories = session.scalars(select(Category).order_by(Category.sort_order)).all()
        assert [category.slug for category in categories] == [
            "artificial-intelligence",
            "ai-agents",
            "software-engineering",
            "open-models",
            "technology-companies",
            "research",
            "economics-finance",
            "international-tech",
        ]
    command.check(migration_config)


def test_repeated_upgrade_preserves_user_changes(database, migration_config):
    with Session(database) as session, session.begin():
        categories = session.scalars(select(Category).order_by(Category.id)).all()
        categories[0].name = "My AI news"
        session.delete(categories[-1])
        session.add(Source(name="My source", feed_url="https://example.com/feed"))
    command.upgrade(migration_config, "head")
    with Session(database) as session:
        categories = session.scalars(select(Category).order_by(Category.id)).all()
        assert len(categories) == 7
        assert categories[0].name == "My AI news"
        assert session.scalar(select(Source)).name == "My source"


def test_downgrade_and_upgrade_on_disposable_database(database, migration_config):
    command.downgrade(migration_config, "base")
    assert set(inspect(database).get_table_names()) == {"alembic_version"}
    command.upgrade(migration_config, "head")
    with Session(database) as session:
        assert len(session.scalars(select(Category)).all()) == 8


def test_offline_sql_does_not_create_a_database(migration_config):
    output = StringIO()
    migration_config.output_buffer = output
    command.upgrade(migration_config, "head", sql=True)
    assert "CREATE TABLE articles" in output.getvalue()
    assert "INSERT INTO categories" in output.getvalue()
    database_url = resolve_database_url(migration_config.get_main_option("sqlalchemy.url"))
    if database_url.get_backend_name() == "sqlite":
        assert not Path(database_url.database).exists()
    else:
        assert "CREATE SCHEMA IF NOT EXISTS tnr" in output.getvalue()
        assert "TIMESTAMP WITH TIME ZONE" in output.getvalue()
