from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, func, inspect, select
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.db import BACKEND_ROOT, create_database_engine, resolve_database_url
from app.models import LOCAL_OWNER_ID, Article, ArticleReadState, Category, CollectionRun, Source


def add_source(session: Session, feed_url: str = "https://example.com/feed") -> Source:
    source = Source(name="Example", feed_url=feed_url)
    session.add(source)
    session.flush()
    return source


def test_database_path_is_independent_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert resolve_database_url("sqlite:///data/news.db").database == str(
        BACKEND_ROOT / "data" / "news.db"
    )
    assert resolve_database_url("sqlite:///:memory:").database == ":memory:"


def test_nested_database_directory_is_created_only_when_engine_is_requested(tmp_path):
    path = tmp_path / "nested" / "news.db"
    url = resolve_database_url(f"sqlite:///{path}")
    assert not path.parent.exists()
    engine = create_database_engine(url)
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert path.exists()
    finally:
        engine.dispose()


def test_foreign_keys_enabled_for_each_connection(database):
    with database.connect() as first, database.connect() as second:
        for connection in (first, second):
            if database.dialect.name == "sqlite":
                assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            else:
                assert (
                    connection.exec_driver_sql("SHOW session_replication_role").scalar_one()
                    == "origin"
                )


def test_data_survives_engine_restart_with_dates_and_read_status(database):
    published = datetime(2026, 11, 5, 12, 30, tzinfo=timezone(timedelta(hours=2)))
    original_url = "https://example.com/article?ref=feed#section"
    with Session(database) as session, session.begin():
        source = add_source(session)
        article = Article(
            source_id=source.id,
            guid="entry-1",
            url=original_url,
            title="An article",
            published_at=published,
        )
        session.add(article)
        session.flush()
        assert source.enabled is True
        assert source.refresh_interval_minutes == 60
        assert source.consecutive_failures == 0
        assert session.get(ArticleReadState, (LOCAL_OWNER_ID, article.id)) is None
        session.add(ArticleReadState(user_id=LOCAL_OWNER_ID, article_id=article.id))
        article_id = article.id
    url = database.url
    database.dispose()
    reopened = create_database_engine(url)
    try:
        with Session(reopened) as session:
            article = session.get(Article, article_id)
            assert article.url == original_url
            assert article.guid == "entry-1"
            assert session.get(ArticleReadState, (LOCAL_OWNER_ID, article.id)) is not None
            assert article.published_at == published.astimezone(UTC)
            assert article.published_at.tzinfo == UTC
            assert article.fetched_at.tzinfo == UTC
    finally:
        reopened.dispose()


def test_missing_publication_date_is_not_replaced_with_fetch_date(database):
    with Session(database) as session, session.begin():
        source = add_source(session)
        session.add(Article(source_id=source.id, url="https://example.com/a", title="No date"))
    with Session(database) as session:
        article = session.scalar(select(Article))
        assert article.published_at is None
        assert article.fetched_at.tzinfo == UTC


@pytest.mark.parametrize(
    ("guid", "url"),
    [("entry-1", "https://example.com/new-link"), ("changed-guid", "https://example.com/a")],
)
def test_duplicate_guid_or_url_is_rejected_for_the_same_source(database, guid, url):
    with Session(database) as session:
        source = add_source(session)
        session.add(
            Article(source_id=source.id, guid="entry-1", url="https://example.com/a", title="First")
        )
        session.commit()
        session.add(Article(source_id=source.id, guid=guid, url=url, title="Duplicate"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert session.scalar(select(func.count()).select_from(Article)) == 1


def test_deduplication_is_source_scoped_and_missing_guids_are_allowed(database):
    with Session(database) as session, session.begin():
        first = add_source(session)
        second = add_source(session, "https://other.example/feed")
        for source in (first, second):
            session.add(
                Article(source_id=source.id, guid="same-id", url="https://example.com/a", title="A")
            )
        session.add_all(
            [
                Article(source_id=first.id, url="https://example.com/b", title="B"),
                Article(source_id=first.id, url="https://example.com/c", title="C"),
            ]
        )
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Article)) == 4


@pytest.mark.parametrize("field", ["name", "slug"])
def test_category_name_and_slug_are_unique(database, field):
    with Session(database) as session:
        existing = session.scalar(select(Category).limit(1))
        values = {"name": "Custom", "slug": "custom"}
        values[field] = getattr(existing, field)
        session.add(Category(**values))
        with pytest.raises(IntegrityError):
            session.commit()


def test_source_feed_url_is_unique(database):
    with Session(database) as session:
        add_source(session)
        with pytest.raises(IntegrityError):
            add_source(session)


@pytest.mark.parametrize(
    "values",
    [
        {"refresh_interval_minutes": 0},
        {"refresh_interval_minutes": -1},
        {"consecutive_failures": -1},
        {"category_id": 99999},
        {"name": " "},
        {"feed_url": ""},
    ],
)
def test_invalid_source_is_rejected(database, values):
    with Session(database) as session:
        fields = {"name": "Example", "feed_url": "https://example.com/feed"} | values
        session.add(Source(**fields))
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize("model", [Article, CollectionRun])
def test_rows_cannot_reference_a_missing_source(database, model):
    fields = {"source_id": 99999}
    if model is Article:
        fields |= {"title": "Orphan", "url": "https://example.com/a"}
    with Session(database) as session:
        session.add(model(**fields))
        with pytest.raises(IntegrityError):
            session.commit()


def test_category_deletion_keeps_sources_and_source_deletion_cascades(database):
    with Session(database) as session, session.begin():
        category = session.scalar(select(Category).limit(1))
        source = add_source(session)
        source.category = category
        other = add_source(session, "https://other.example/feed")
        session.add_all(
            [
                Article(source_id=source.id, url="https://example.com/a", title="A"),
                Article(source_id=other.id, url="https://example.com/b", title="B"),
                CollectionRun(source_id=source.id),
            ]
        )
        category_id, source_id = category.id, source.id
    with Session(database) as session, session.begin():
        session.execute(delete(Category).where(Category.id == category_id))
    with Session(database) as session, session.begin():
        assert session.get(Source, source_id).category is None
        assert session.scalar(select(func.count()).select_from(Article)) == 2
        session.execute(delete(Source).where(Source.id == source_id))
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Source)) == 1
        assert session.scalar(select(func.count()).select_from(Article)) == 1
        assert session.scalar(select(func.count()).select_from(CollectionRun)) == 0


def test_naive_timestamps_are_rejected(database):
    with Session(database) as session:
        session.add(
            Source(
                name="Example", feed_url="https://example.com/feed", created_at=datetime(2026, 1, 1)
            )
        )
        with pytest.raises(StatementError, match="must include a timezone"):
            session.commit()


@pytest.mark.parametrize(
    "values",
    [
        {"status": "invalid"},
        {"status": "success"},
        {"articles_seen": -1},
        {"articles_added": -1},
        {"articles_seen": 1, "articles_added": 2},
        {"finished_at": datetime(2026, 1, 2, tzinfo=UTC)},
        {"status": "error", "finished_at": datetime(2025, 12, 31, tzinfo=UTC)},
    ],
)
def test_collection_run_constraints(database, values):
    with Session(database) as session:
        source = add_source(session)
        session.add(
            CollectionRun(
                source_id=source.id, started_at=datetime(2026, 1, 1, tzinfo=UTC), **values
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize("status", ["success", "not_modified", "error"])
def test_collection_run_can_finish(database, status):
    with Session(database) as session, session.begin():
        source = add_source(session)
        run = CollectionRun(source_id=source.id)
        session.add(run)
        session.flush()
        run.status = status
        run.finished_at = run.started_at + timedelta(seconds=1)
    with Session(database) as session:
        stored = session.scalar(select(CollectionRun))
        assert stored.status == status
        assert stored.finished_at.tzinfo == UTC


def test_database_rolls_back_data_and_ddl(database):
    with Session(database) as session:
        add_source(session)
        # Closing a session without commit must discard the write.
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Source)) == 0
    with database.connect() as connection:
        connection.exec_driver_sql("CREATE TABLE rollback_probe (id INTEGER)")
        connection.rollback()
    assert "rollback_probe" not in inspect(database).get_table_names()
