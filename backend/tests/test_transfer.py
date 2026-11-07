from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import URL, text
from sqlalchemy.exc import SQLAlchemyError

from app import transfer
from app.config import Settings
from app.db import create_database_engine
from app.main import create_app
from app.models import (
    LOCAL_OWNER_ID,
    AppUser,
    Article,
    ArticleReadState,
    Category,
    CollectionRun,
    Source,
    Subscription,
)

READER = UUID("00000000-0000-0000-0000-000000000002")
REVOKED = UUID("00000000-0000-0000-0000-000000000003")
STAMP = datetime(2026, 11, 6, 14, 37, 2, 123456, tzinfo=timezone(timedelta(hours=2)))


@pytest.fixture
def snapshot(tmp_path):
    path = tmp_path / "snapshot 100%.db"
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    url = URL.create("sqlite", database=str(path))
    config.set_main_option("sqlalchemy.url", url.render_as_string().replace("%", "%%"))
    command.upgrade(config, "head")
    engine = create_database_engine(url)
    with engine.begin() as connection:
        connection.execute(
            AppUser.__table__.update().values(
                display_name="Owner",
                supabase_subject=uuid4(),
                created_at=STAMP,
            )
        )
        connection.execute(
            AppUser.__table__.insert(),
            [
                {
                    "id": READER,
                    "supabase_subject": uuid4(),
                    "display_name": "Reader",
                    "role": "reader",
                    "active": True,
                    "created_at": STAMP,
                },
                {
                    "id": REVOKED,
                    "supabase_subject": uuid4(),
                    "display_name": "Revoked",
                    "role": "reader",
                    "active": False,
                    "created_at": STAMP,
                },
            ],
        )
        # Edited seeds, deleted seeds, and reused names at different IDs must all survive.
        connection.execute(Category.__table__.delete())
        connection.execute(
            Category.__table__.insert(),
            [
                {
                    "id": 2,
                    "name": "Artificial intelligence and LLMs",
                    "slug": "artificial-intelligence",
                    "sort_order": 9,
                },
                {"id": 71, "name": "Ricerca 🧪", "slug": "research-new", "sort_order": 0},
            ],
        )
        connection.execute(
            Source.__table__.insert(),
            [
                {
                    "id": 11,
                    "name": "Shared",
                    "feed_url": "https://example.org/rss",
                    "category_id": 71,
                    "enabled": True,
                    "etag": 'W/"v1"',
                    "last_error": None,
                    "created_at": STAMP,
                },
                {
                    "id": 23,
                    "name": "Unfollowed",
                    "feed_url": "https://example.org/other",
                    "category_id": None,
                    "enabled": False,
                    "etag": None,
                    "last_error": "Old error",
                    "created_at": STAMP,
                },
            ],
        )
        connection.execute(
            Article.__table__.insert(),
            [
                {
                    "id": 101,
                    "source_id": 11,
                    "guid": "é" * 1000,
                    "url": "https://example.org/a",
                    "title": "AI e caffè 🧪",
                    "description": "<b>Untrusted HTML</b>",
                    "published_at": STAMP,
                    "fetched_at": STAMP,
                },
                {
                    "id": 305,
                    "source_id": 23,
                    "guid": None,
                    "url": "https://example.org/b",
                    "title": "Unfollowed story",
                    "description": None,
                    "published_at": None,
                    "fetched_at": STAMP,
                },
            ],
        )
        connection.execute(
            CollectionRun.__table__.insert(),
            [
                {
                    "id": 82,
                    "source_id": 11,
                    "started_at": STAMP,
                    "finished_at": STAMP + timedelta(seconds=5),
                    "status": "success",
                    "articles_seen": 1,
                    "articles_added": 1,
                },
            ],
        )
        connection.execute(
            Subscription.__table__.insert(),
            [
                {"user_id": user, "source_id": 11, "created_at": STAMP}
                for user in (LOCAL_OWNER_ID, READER, REVOKED)
            ],
        )
        connection.execute(
            ArticleReadState.__table__.insert(),
            [
                {"user_id": LOCAL_OWNER_ID, "article_id": 101, "read_at": STAMP},
                {"user_id": READER, "article_id": 305, "read_at": STAMP},
            ],
        )
    engine.dispose()
    return path


@pytest.fixture
def target(database):
    if database.dialect.name != "postgresql":
        pytest.skip("Transfer integration requires --postgres with a disposable local server")
    return database


def run_transfer(snapshot, target):
    return transfer.rehearse(
        snapshot, transfer.snapshot_hash(snapshot), target.url.render_as_string(hide_password=False)
    )


@pytest.mark.parametrize(
    "url",
    [
        "",
        "sqlite:///data/news.db",
        "postgresql://admin:secret@example.com/tnr_transfer_12345678",
        "postgresql://admin:secret@localhost:5432/tnr_transfer_12345678?sslmode=disable",
        "postgresql://admin:secret@127.0.0.1:5432/postgres?sslmode=disable",
        "postgresql://admin:secret@127.0.0.1/tnr_transfer_12345678?sslmode=disable",
        "postgresql://admin:secret@127.0.0.1:5432/tnr_transfer_12345678?host=example.com&sslmode=disable",
    ],
)
def test_rejects_non_disposable_or_remote_target_without_connecting(url, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Must reject the destination before reading or connecting")

    monkeypatch.setattr(transfer, "read_snapshot", forbidden)
    monkeypatch.setattr(transfer, "create_database_engine", forbidden)
    with pytest.raises(transfer.TransferError):
        transfer.rehearse(Path("missing.db"), "0" * 64, url)


def test_libpq_cannot_override_loopback(monkeypatch):
    monkeypatch.setenv("PGHOSTADDR", "192.0.2.1")
    with pytest.raises(transfer.TransferError, match="overrides"):
        transfer.local_target_url(
            "postgresql://a@127.0.0.1:5432/tnr_transfer_12345678?sslmode=disable"
        )


def test_reads_verified_snapshot_without_changing_it(snapshot):
    digest = transfer.snapshot_hash(snapshot)
    rows = transfer.read_snapshot(snapshot, digest)
    assert rows["app_users"][0]["created_at"] == STAMP.astimezone(UTC)
    assert len(rows["article_read_states"]) == 2
    assert transfer.snapshot_hash(snapshot) == digest
    assert not list(snapshot.parent.glob("*.db-*"))
    with pytest.raises(transfer.TransferError, match="SHA-256"):
        transfer.read_snapshot(snapshot, "0" * 64)


@pytest.mark.parametrize(
    "change, message",
    [
        ("UPDATE alembic_version SET version_num='0003'", "revision"),
        ("CREATE TABLE forgotten_data (id INTEGER)", "tables"),
        ("UPDATE collection_runs SET status='running', finished_at=NULL", "unfinished"),
        ("UPDATE articles SET source_id=9999", "foreign key"),
    ],
)
def test_rejects_incomplete_or_inconsistent_snapshot(snapshot, change, message):
    import sqlite3

    with sqlite3.connect(snapshot) as connection:
        connection.execute(change)
    with pytest.raises(transfer.TransferError, match=message):
        transfer.read_snapshot(snapshot, transfer.snapshot_hash(snapshot))


def test_rejects_unhashed_sidecar(snapshot):
    snapshot.with_name(snapshot.name + "-wal").write_bytes(b"unhashed data")
    with pytest.raises(transfer.TransferError, match="sidecars"):
        transfer.read_snapshot(snapshot, transfer.snapshot_hash(snapshot))


def test_transfer_preserves_every_row_and_resets_all_sequences(snapshot, target):
    digest = transfer.snapshot_hash(snapshot)
    expected = transfer.read_snapshot(snapshot, digest)
    report = run_transfer(snapshot, target)
    assert report["snapshot_sha256"] == digest
    with target.begin() as connection:
        for table in transfer.TABLES:
            assert transfer.read_rows(connection, table) == expected[table.name]
            assert report["tables"][table.name]["count"] == len(expected[table.name])
        new_category = connection.execute(
            Category.__table__.insert().values(name="Next", slug="next").returning(Category.id)
        ).scalar_one()
        new_source = connection.execute(
            Source.__table__.insert()
            .values(name="Next", feed_url="https://example.org/next")
            .returning(Source.id)
        ).scalar_one()
        new_article = connection.execute(
            Article.__table__.insert()
            .values(source_id=new_source, title="Next", url="https://example.org/next")
            .returning(Article.id)
        ).scalar_one()
        new_run = connection.execute(
            CollectionRun.__table__.insert()
            .values(source_id=new_source)
            .returning(CollectionRun.id)
        ).scalar_one()
        assert (new_category, new_source, new_article, new_run) == (72, 24, 306, 83)
    assert transfer.snapshot_hash(snapshot) == digest
    with pytest.raises(transfer.TransferError, match="beyond"):
        run_transfer(snapshot, target)


@pytest.mark.parametrize(
    "change",
    [
        "UPDATE categories SET name='Changed' WHERE id=1",
        "UPDATE app_users SET active=false",
    ],
)
def test_does_not_replace_modified_target_seeds(snapshot, target, change):
    with target.begin() as connection:
        connection.execute(text(change))
        before = {table.name: transfer.read_rows(connection, table) for table in transfer.TABLES}
    with pytest.raises(transfer.TransferError, match="beyond"):
        run_transfer(snapshot, target)
    with target.connect() as connection:
        assert {
            table.name: transfer.read_rows(connection, table) for table in transfer.TABLES
        } == before


@pytest.mark.parametrize("failure", ["constraint", "verification"])
def test_failure_rolls_back_owner_categories_rows_and_sequences(
    snapshot, target, monkeypatch, failure
):
    with target.connect() as connection:
        before = {table.name: transfer.read_rows(connection, table) for table in transfer.TABLES}
        sequences = {
            name: connection.exec_driver_sql(
                f"SELECT last_value, is_called FROM tnr.{name}_id_seq"
            ).one()
            for name in transfer.SEQUENCED_TABLES
        }
    if failure == "constraint":
        source = create_database_engine(URL.create("sqlite", database=str(snapshot)))
        with source.begin() as connection:
            # SQLite permits this length; PostgreSQL's varchar(1024) rejects it mid-transfer.
            connection.execute(
                Article.__table__.update().where(Article.id == 101).values(guid="x" * 1025)
            )
        source.dispose()
        expected_error = SQLAlchemyError
    else:
        original = transfer.verify_rows

        def corrupt_before_verification(connection, rows):
            connection.execute(
                Article.__table__.update()
                .where(Article.id == 101)
                .values(title="Unexpected change")
            )
            return original(connection, rows)

        monkeypatch.setattr(transfer, "verify_rows", corrupt_before_verification)
        expected_error = transfer.TransferError
    with pytest.raises(expected_error):
        run_transfer(snapshot, target)
    with target.connect() as connection:
        assert {
            table.name: transfer.read_rows(connection, table) for table in transfer.TABLES
        } == before
        for name in transfer.SEQUENCED_TABLES:
            assert (
                connection.exec_driver_sql(
                    f"SELECT last_value, is_called FROM tnr.{name}_id_seq"
                ).one()
                == sequences[name]
            )


@pytest.mark.anyio
async def test_transferred_accounts_keep_permissions_preferences_and_reads(snapshot, target):
    run_transfer(snapshot, target)
    app = create_app(
        Settings(
            _env_file=None,
            database_url=target.url.render_as_string(hide_password=False),
            local_user_id=LOCAL_OWNER_ID,
            scheduler_enabled=False,
        )
    )
    # Substitute only verified identity, as in existing multiuser tests; real access checks run.
    from app.api.dependencies import get_identity

    current_user = LOCAL_OWNER_ID
    app.dependency_overrides[get_identity] = lambda: current_user
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/api/articles?is_read=true")).json()["total"] == 1
            current_user = READER
            assert (await client.get("/api/articles?is_read=true")).json()["total"] == 0
            assert (await client.get("/api/articles?is_read=false")).json()["items"][0]["id"] == 101
            assert (
                await client.post("/api/categories", json={"name": "Denied", "slug": "denied"})
            ).status_code == 403
            assert (await client.put("/api/subscriptions/23")).status_code == 204
            assert (await client.get("/api/articles?is_read=true")).json()["items"][0]["id"] == 305
            current_user = LOCAL_OWNER_ID
            assert (await client.get("/api/subscriptions")).json()["total"] == 1
            current_user = REVOKED
            assert (await client.get("/api/articles")).status_code == 403
            current_user = uuid4()
            assert (await client.get("/api/articles")).status_code == 403


def test_cli_never_inherits_remote_operator_url(monkeypatch, capsys):
    monkeypatch.delenv("TNR_TRANSFER_DATABASE_URL", raising=False)
    monkeypatch.setenv("TNR_MIGRATION_DATABASE_URL", "postgresql://secret@remote/postgres")
    monkeypatch.setattr("sys.argv", ["transfer", "--snapshot", "missing.db", "--sha256", "0" * 64])
    with pytest.raises(SystemExit) as result:
        transfer.main()
    assert result.value.code == 1
    assert "secret" not in capsys.readouterr().err


def test_empty_tables_start_sequences_at_one(snapshot, target, monkeypatch, capsys):
    import json

    source = create_database_engine(URL.create("sqlite", database=str(snapshot)))
    with source.begin() as connection:
        for table in reversed(transfer.TABLES):
            if table.name != "app_users":
                connection.execute(table.delete())
    source.dispose()
    monkeypatch.setenv(
        "TNR_TRANSFER_DATABASE_URL", target.url.render_as_string(hide_password=False)
    )
    monkeypatch.setattr(
        "sys.argv",
        ["transfer", "--snapshot", str(snapshot), "--sha256", transfer.snapshot_hash(snapshot)],
    )
    assert transfer.main() == 0
    assert json.loads(capsys.readouterr().out)["tables"]["articles"]["count"] == 0
    with target.connect() as connection:
        for name in transfer.SEQUENCED_TABLES:
            assert (
                connection.execute(text(f"SELECT nextval('tnr.{name}_id_seq')")).scalar_one() == 1
            )


def test_target_writes_are_blocked_until_verification_completes(snapshot, target, monkeypatch):
    original = transfer.verify_rows

    def verify_while_another_writer_attempts(connection, rows):
        with pytest.raises(SQLAlchemyError) as error, target.begin() as competing:
            competing.exec_driver_sql("SET LOCAL lock_timeout='50ms'")
            competing.exec_driver_sql(
                "UPDATE tnr.categories SET name='Concurrent change' WHERE id=2"
            )
        assert error.value.orig.sqlstate == "55P03"
        return original(connection, rows)

    monkeypatch.setattr(transfer, "verify_rows", verify_while_another_writer_attempts)
    run_transfer(snapshot, target)
