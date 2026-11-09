"""Connection checks run offline; storage checks also run with pytest --postgres."""

from datetime import UTC, datetime
from io import StringIO

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import BACKEND_ROOT, create_database_engine, resolve_database_url
from app.models import Article, Source


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+psycopg"])
def test_postgres_url_selects_psycopg_and_verified_tls(scheme):
    url = resolve_database_url(f"{scheme}://reader:p%40ss%25@db.example.org/news")
    assert url.drivername == "postgresql+psycopg"
    assert url.password == "p@ss%"
    assert url.query["sslmode"] == "verify-full"


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://reader:secret@db.example.org/news?sslmode=require",
        "postgresql://reader:secret@db.example.org/news?sslmode=disable",
        "postgresql://reader:secret@db.example.org:6543/news",
        "postgresql://reader:secret@127.0.0.1/news?host=db.example.org&sslmode=disable",
        "postgresql://reader:secret@db.example.org/news?options=-csearch_path=public",
        "postgresql://reader:secret@/news",
        "postgresql+psycopg2://reader:secret@db.example.org/news",
        "mysql://reader:secret@db.example.org/news",
    ],
)
def test_unsupported_connection_options_fail_without_disclosing_credentials(url):
    with pytest.raises(ValueError) as error:
        resolve_database_url(url)
    assert "secret" not in str(error.value)


def test_postgres_engine_is_lazy_and_pool_is_bounded(monkeypatch):
    import psycopg

    def no_connection(*args, **kwargs):
        pytest.fail("Engine construction must not connect or migrate")

    monkeypatch.setattr(psycopg, "connect", no_connection)
    engine = create_database_engine("postgresql://reader:secret@db.example.org/news")
    try:
        assert engine.dialect.driver == "psycopg"
        assert engine.pool.size() == 3
        assert engine.pool.timeout() == 10
    finally:
        engine.dispose()


def test_postgresql_offline_migration_without_server():
    output = StringIO()
    config = Config(str(BACKEND_ROOT / "alembic.ini"), output_buffer=output)
    config.set_main_option("sqlalchemy.url", "postgresql://reader:secret@db.example.org/news")
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert sql.index("CREATE SCHEMA") < sql.index("CREATE TABLE categories")
    assert "SET LOCAL search_path TO tnr" in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql
    assert "AT TIME ZONE 'UTC'" in sql
    assert "EXCLUDE USING hash" in sql
    assert "REVOKE ALL ON SCHEMA tnr FROM PUBLIC" in sql
    assert "%%I" not in sql
    assert "secret" not in sql


def test_long_unicode_keys_and_exact_duplicates(database):
    # Different code points prevent TOAST compression from hiding the B-tree limit.
    key = "".join(chr(0x4E00 + i) for i in range(1000))
    with Session(database) as session:
        source = Source(name="Unicode", feed_url="https://example.org/" + key * 2)
        session.add(source)
        session.flush()
        source_id = source.id
        session.add(
            Article(
                source_id=source_id,
                guid=key,
                url="https://example.org/" + key * 2,
                title="Long Unicode key",
            )
        )
        session.commit()
        stored = session.scalar(select(Article))
        assert stored.guid == key
        for field in ("guid", "url"):
            values = {
                "source_id": source_id,
                "guid": "other",
                "url": "https://example.org/other",
                "title": "Duplicate",
            }
            values[field] = getattr(stored, field)
            session.add(Article(**values))
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()


@pytest.mark.anyio
async def test_search_and_source_order_preserve_sqlite_semantics(database, client):
    with Session(database) as session, session.begin():
        for number, name in enumerate(["ä", "z", "Ä", "A", "a"]):
            source = Source(name=name, feed_url=f"https://example.org/{number}")
            session.add(source)
            session.flush()
            session.add(
                Article(
                    source_id=source.id,
                    title=f"{name} NEWS 100%_ /",
                    url=f"https://example.org/article/{number}",
                )
            )
    sources = (await client.get("/api/sources")).json()["items"]
    assert [source["name"] for source in sources] == ["A", "a", "z", "Ä", "ä"]
    for query, count in [("news", 5), ("ä", 1), ("Ä", 1), ("a news", 2), ("100%_ /", 5)]:
        response = await client.get(
            "/api/articles", params={"q": query, "subscribed_only": "false"}
        )
        assert response.status_code == 200
        assert response.json()["total"] == count


def test_upgrade_from_0001_preserves_existing_data(migration_config):
    command.upgrade(migration_config, "0001")
    engine = create_database_engine(migration_config.get_main_option("sqlalchemy.url"))
    try:
        with engine.begin() as connection:
            connection.execute(
                text("""
                INSERT INTO sources (name, feed_url, created_at)
                VALUES ('Existing', 'https://example.org/feed', '2026-01-02 03:04:05')
            """)
            )
            if engine.dialect.name == "postgresql":
                # Simulate broad grants before upgrading, rather than only testing defaults.
                connection.exec_driver_sql("GRANT ALL ON SCHEMA tnr TO PUBLIC")
                connection.exec_driver_sql("GRANT ALL ON ALL TABLES IN SCHEMA tnr TO PUBLIC")
                connection.exec_driver_sql("GRANT ALL ON ALL SEQUENCES IN SCHEMA tnr TO PUBLIC")
        command.upgrade(migration_config, "head")
        with Session(engine) as session:
            stored = session.scalar(select(Source))
            assert stored.name == "Existing"
            assert stored.created_at == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
        command.check(migration_config)
        if engine.dialect.name == "postgresql":
            with engine.connect() as connection:
                assert (
                    connection.exec_driver_sql("""
                    SELECT count(*) FROM pg_namespace n, aclexplode(n.nspacl) a
                    WHERE n.nspname = 'tnr' AND a.grantee = 0
                """).scalar_one()
                    == 0
                )
    finally:
        engine.dispose()


def test_postgres_exported_sql_applies_to_empty_database(migration_config):
    url = resolve_database_url(migration_config.get_main_option("sqlalchemy.url"))
    if url.get_backend_name() != "postgresql":
        pytest.skip("Run with --postgres to apply the exported SQL")
    output = StringIO()
    migration_config.output_buffer = output
    command.upgrade(migration_config, "head", sql=True)
    engine = create_database_engine(url)
    try:
        # Match psql: send the literal script, without DBAPI parameter interpolation.
        with engine.connect() as connection:
            raw = connection.connection.driver_connection
            raw.autocommit = True
            with raw.cursor() as cursor:
                cursor.execute(output.getvalue(), prepare=False)
            raw.autocommit = False
        command.check(migration_config)
        with Session(engine) as session:
            assert session.scalar(text("SELECT count(*) FROM categories")) == 8
    finally:
        engine.dispose()


def test_postgres_namespace_privileges_and_storage(database):
    if database.dialect.name != "postgresql":
        pytest.skip("Run with --postgres to check PostgreSQL storage and privileges")
    with database.connect() as connection:
        assert connection.exec_driver_sql("SHOW search_path").scalar_one() == "tnr"
        assert connection.exec_driver_sql("SHOW TimeZone").scalar_one() == "UTC"
        assert not set(inspect(connection).get_table_names(schema="public")) & {
            "sources",
            "articles",
            "categories",
            "collection_runs",
            "alembic_version",
            "app_users",
            "subscriptions",
            "article_read_states",
            "reader_invitations",
            "source_proposals",
        }
        assert (
            connection.exec_driver_sql("""
            SELECT count(*) FROM pg_namespace n, aclexplode(n.nspacl) a
            WHERE n.nspname = 'tnr' AND a.grantee = 0
        """).scalar_one()
            == 0
        )
        for role in connection.exec_driver_sql("""
            SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated', 'service_role')
        """).scalars():
            assert not connection.execute(
                text("SELECT has_schema_privilege(:role, 'tnr', 'USAGE')"), {"role": role}
            ).scalar_one()
            for table in (
                "articles",
                "app_users",
                "subscriptions",
                "article_read_states",
                "reader_invitations",
                "source_proposals",
            ):
                assert not connection.execute(
                    text("SELECT has_table_privilege(:role, :table, 'SELECT')"),
                    {"role": role, "table": f"tnr.{table}"},
                ).scalar_one()
        constraints = (
            connection.exec_driver_sql("""
            SELECT conname FROM pg_constraint c JOIN pg_namespace n ON c.connamespace = n.oid
            WHERE n.nspname = 'tnr' AND contype = 'x'
        """)
            .scalars()
            .all()
        )
        assert set(constraints) == {
            "uq_sources_feed_url",
            "uq_articles_source_guid",
            "uq_articles_source_url",
        }
        with Session(connection) as session:
            source = Source(name="Timezone", feed_url="https://example.org/feed")
            session.add(source)
            session.commit()
            source_id = source.id
        connection.exec_driver_sql("SET TIME ZONE 'Pacific/Auckland'")
        with Session(connection) as session:
            assert session.get(Source, source_id).created_at.tzinfo == UTC
