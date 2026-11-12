from io import StringIO

from alembic import command
from db_assertions import TABLES, read_rows
from sqlalchemy import MetaData, Table, insert, inspect, select, update
from sqlalchemy.orm import Session

from app.db import resolve_database_url
from app.models import (
    LOCAL_OWNER_ID,
    Article,
    ArticleReadState,
    Category,
    Source,
    Subscription,
)


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
        "reader_invitations",
        "source_proposals",
        "ai_brief_budget",
        "ai_brief_control",
        "ai_brief_jobs",
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


def test_discussion_migration_cleans_only_hacker_news_placeholder(database, migration_config):
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    command.downgrade(migration_config, "0010")
    with database.begin() as connection:
        articles = Table("articles", MetaData(), autoload_with=connection)
        sources = Table("sources", MetaData(), autoload_with=connection)
        for name, url in [
            ("HN", "https://news.ycombinator.com/rss"),
            ("Other", "https://example.org/rss"),
        ]:
            source_id = connection.scalar(
                insert(sources)
                .values(name=name, feed_url=url, etag='"old"', created_at=now)
                .returning(sources.c.id)
            )
            connection.execute(
                insert(articles).values(
                    source_id=source_id,
                    title=name,
                    url="https://example.org/a",
                    description="Comments",
                    fetched_at=now,
                )
            )
    command.upgrade(migration_config, "head")
    command.check(migration_config)
    with Session(database) as session:
        entries = {item.title: item for item in session.scalars(select(Article))}
        assert entries["HN"].description is None
        assert entries["HN"].discussion_url is None
        assert entries["Other"].description == "Comments"
        assert entries["HN"].source.etag is None
        assert entries["Other"].source.etag == '"old"'
    command.downgrade(migration_config, "0010")
    assert "discussion_url" not in {
        column["name"] for column in inspect(database).get_columns("articles")
    }
    command.upgrade(migration_config, "head")


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


def test_invitation_migration_preserves_existing_profiles_and_personal_data(
    database, migration_config
):
    command.downgrade(migration_config, "0004")
    with Session(database) as session, session.begin():
        users = Table("app_users", MetaData(), autoload_with=database)
        session.execute(
            update(users).where(users.c.id == LOCAL_OWNER_ID).values(display_name="Existing owner")
        )
        source_id = session.scalar(
            insert(Source)
            .values(name="Preserved source", feed_url="https://example.org/preserved")
            .returning(Source.id)
        )
        article_id = session.scalar(
            insert(Article)
            .values(source_id=source_id, title="Preserved article", url="https://example.org/a")
            .returning(Article.id)
        )
        session.add_all(
            [
                Subscription(user_id=LOCAL_OWNER_ID, source_id=source_id),
                ArticleReadState(user_id=LOCAL_OWNER_ID, article_id=article_id),
            ]
        )
    tables = [
        Table(table.name, MetaData(), autoload_with=database)
        for table in TABLES
        if table.name
        not in {
            "reader_invitations",
            "source_proposals",
            "ai_brief_control",
            "ai_brief_jobs",
            "ai_brief_budget",
        }
    ]
    with database.connect() as connection:
        before = {table.name: read_rows(connection, table) for table in tables}
    command.upgrade(migration_config, "head")
    command.check(migration_config)
    with database.connect() as connection:
        assert {table.name: read_rows(connection, table) for table in tables} == before
        assert "reader_invitations" in inspect(connection).get_table_names()


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
    resolve_database_url(migration_config.get_main_option("sqlalchemy.url"))
    assert "CREATE SCHEMA IF NOT EXISTS tnr" in output.getvalue()
    assert "TIMESTAMP WITH TIME ZONE" in output.getvalue()


def test_attempt_migration_preserves_content_and_backfills_interrupted_runs(
    database, migration_config
):
    from datetime import UTC, datetime

    from app.models import CollectionRun

    command.downgrade(migration_config, "0009")
    started = datetime(2026, 11, 9, tzinfo=UTC)
    with Session(database) as session, session.begin():
        source_id = session.scalar(
            insert(Source)
            .values(name="Existing", feed_url="https://example.org/rss")
            .returning(Source.id)
        )
        session.add(CollectionRun(source_id=source_id, started_at=started))
        session.execute(
            insert(Article).values(
                source_id=source_id, title="Preserved", url="https://example.org/a"
            )
        )
    command.upgrade(migration_config, "head")
    command.upgrade(migration_config, "head")
    command.check(migration_config)
    with Session(database) as session:
        assert session.get(Source, source_id).last_attempt_at == started
        assert session.scalar(select(CollectionRun)).status == "running"
        assert session.scalar(select(Article)).title == "Preserved"
