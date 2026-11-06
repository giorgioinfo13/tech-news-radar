import asyncio
from contextlib import AsyncExitStack
from uuid import UUID, uuid4

import pytest
from alembic import command
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_identity
from app.collection.download import Download
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


@pytest.fixture
async def people(database):
    ids = {"admin": LOCAL_OWNER_ID, "alice": uuid4(), "bob": uuid4()}
    with Session(database) as session, session.begin():
        session.add_all(
            [AppUser(id=ids[name], display_name=name, active=True) for name in ("alice", "bob")]
        )
        source = Source(name="Shared", feed_url="https://example.org/feed", category_id=1)
        session.add(source)
        session.flush()
        article = Article(source_id=source.id, title="Shared AI story", url="https://example.org/a")
        session.add(article)
        session.flush()
        source_id, article_id = source.id, article.id
    app = create_app(
        Settings(
            _env_file=None,
            database_url=database.url.render_as_string(hide_password=False),
            scheduler_enabled=False,
        )
    )

    # Test-only verified-identity substitute. Production has no identity header support.
    def identity(request: Request) -> UUID:
        return UUID(request.headers["x-test-user"])

    app.dependency_overrides[get_identity] = identity
    async with app.router.lifespan_context(app), AsyncExitStack() as stack:
        clients = {
            name: await stack.enter_async_context(
                AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                    headers={"x-test-user": str(user_id)},
                )
            )
            for name, user_id in ids.items()
        }
        yield clients, ids, source_id, article_id, app


@pytest.mark.anyio
async def test_personal_subscriptions_reads_and_filters(people, database):
    clients, ids, source, article, _ = people
    alice, bob, admin = (clients[name] for name in ("alice", "bob", "admin"))
    for client in clients.values():
        assert (await client.get("/api/articles")).json()["total"] == 0
        assert (await client.get("/api/sources")).json()["total"] == 1
    for client in (alice, bob):
        for _ in range(2):
            assert (await client.put(f"/api/subscriptions/{source}")).status_code == 204
        assert (await client.get("/api/subscriptions?limit=1")).json()["total"] == 1
    assert (await alice.patch(f"/api/articles/{article}", json={"is_read": True})).json()[
        "is_read"
    ] is True
    assert (await alice.get("/api/articles?is_read=true&q=ai&category_id=1")).json()["total"] == 1
    assert (await bob.get("/api/articles?is_read=false&q=ai&category_id=1")).json()["total"] == 1
    assert (await bob.get("/api/articles?is_read=true")).json()["total"] == 0
    assert (await admin.get("/api/articles?subscribed_only=false")).json()["items"][0][
        "is_read"
    ] is False
    assert (await admin.get("/api/subscriptions")).json()["total"] == 0
    for _ in range(2):
        assert (await alice.delete(f"/api/subscriptions/{source}")).status_code == 204
    assert (await alice.get("/api/articles")).json()["total"] == 0
    assert (await bob.get("/api/articles")).json()["total"] == 1
    await alice.put(f"/api/subscriptions/{source}")
    assert (await alice.get("/api/articles")).json()["items"][0]["is_read"] is True
    # IDs supplied by callers do not change ownership, including for an administrator.
    response = await bob.patch(
        f"/api/articles/{article}?user_id={ids['alice']}", json={"is_read": False}
    )
    assert response.status_code == 200
    assert (await alice.get("/api/articles")).json()["items"][0]["is_read"] is True
    assert (
        await bob.patch(
            f"/api/articles/{article}", json={"is_read": True, "user_id": str(ids["alice"])}
        )
    ).status_code == 422
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Article)) == 1
        assert session.scalar(select(func.count()).select_from(ArticleReadState)) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/api/categories", {"name": "Injected", "slug": "injected"}),
        ("PATCH", "/api/categories/1", {"name": "Injected"}),
        ("DELETE", "/api/categories/1", None),
        ("POST", "/api/sources", {"name": "Injected", "feed_url": "https://bad.example/feed"}),
        ("PATCH", "/api/sources/1", {"enabled": False}),
        ("DELETE", "/api/sources/1", None),
    ],
)
async def test_reader_cannot_manage_catalog(people, database, method, path, body):
    clients, _, source, _, _ = people
    result = await clients["alice"].request(method, path, json=body)
    assert result.status_code == 403
    with Session(database) as session:
        assert session.get(Source, source).enabled is True
        assert session.scalar(select(func.count()).select_from(Source)) == 1
        assert session.scalar(select(func.count()).select_from(Category)) == 8


@pytest.mark.anyio
async def test_admin_changes_apply_to_shared_catalog_and_deletes_cascade(people, database):
    clients, ids, source, article, _ = people
    for client in clients.values():
        await client.put(f"/api/subscriptions/{source}")
        await client.patch(f"/api/articles/{article}", json={"is_read": True})
    admin = clients["admin"]
    category = (
        await admin.post(
            "/api/categories", json={"name": "Shared category", "slug": "shared-category"}
        )
    ).json()
    assert (
        await admin.patch(
            f"/api/sources/{source}", json={"category_id": category["id"], "enabled": False}
        )
    ).status_code == 200
    for name in ("alice", "bob"):
        page = (await clients[name].get("/api/articles")).json()
        assert page["items"][0]["source"]["category"]["name"] == "Shared category"
        assert page["items"][0]["is_read"] is True
    assert (await admin.delete(f"/api/categories/{category['id']}")).status_code == 204
    assert (await clients["alice"].get("/api/articles")).json()["items"][0]["source"][
        "category"
    ] is None
    assert (await admin.delete(f"/api/sources/{source}")).status_code == 204
    with Session(database) as session:
        for model in (Subscription, ArticleReadState, Article):
            assert session.scalar(select(func.count()).select_from(model)) == 0
        assert session.get(AppUser, ids["alice"]) is not None


@pytest.mark.anyio
async def test_reader_refresh_requires_subscription_and_uses_shared_cooldown(people, database):
    clients, _, source, _, app = people
    calls = []

    def fetch(*args):
        calls.append(True)
        # Identity lookup must release its connection before HTTP I/O.
        assert app.state.database_engine.pool.checkedout() == 0
        return Download(b"", "https://example.org/feed", not_modified=True)

    app.state.collector.downloader.fetch = fetch
    assert (await clients["alice"].post(f"/api/sources/{source}/refresh")).status_code == 403
    assert calls == []
    for name in ("alice", "bob"):
        await clients[name].put(f"/api/subscriptions/{source}")
    assert (await clients["alice"].post(f"/api/sources/{source}/refresh")).status_code == 200
    assert (await clients["bob"].post(f"/api/sources/{source}/refresh")).status_code == 429
    assert len(calls) == 1
    await clients["admin"].patch(f"/api/sources/{source}", json={"enabled": False})
    assert (await clients["bob"].post(f"/api/sources/{source}/refresh")).status_code == 409
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(CollectionRun)) == 1


@pytest.mark.anyio
async def test_disabled_or_deleted_user_is_denied_on_next_request(people, database):
    clients, ids, source, article, _ = people
    with Session(database) as session, session.begin():
        session.get(AppUser, ids["alice"]).active = False
        session.execute(delete(AppUser).where(AppUser.id == ids["bob"]))
    for name in ("alice", "bob"):
        for path in (
            "/api/me",
            "/api/sources",
            "/api/categories",
            "/api/articles",
            "/api/subscriptions",
            f"/api/sources/{source}/runs",
        ):
            assert (await clients[name].get(path)).status_code == 403
        assert (
            await clients[name].patch(f"/api/articles/{article}", json={"is_read": True})
        ).status_code == 403
        assert (await clients[name].put(f"/api/subscriptions/{source}")).status_code == 403


@pytest.mark.anyio
async def test_repeated_parallel_personal_writes_are_idempotent(people, database):
    clients, ids, source, article, _ = people
    # Sequential operations from independent clients can overlap at the database.
    results = await asyncio.gather(
        *[clients["alice"].put(f"/api/subscriptions/{source}") for _ in range(4)]
    )
    assert {r.status_code for r in results} == {204}
    results = await asyncio.gather(
        *[
            clients["alice"].patch(f"/api/articles/{article}", json={"is_read": True})
            for _ in range(4)
        ]
    )
    assert {r.status_code for r in results} == {200}
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Subscription)) == 1
        assert session.scalar(select(func.count()).select_from(ArticleReadState)) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("identity", "remote", "authorization", "status"),
    [
        (None, False, None, 401),
        (LOCAL_OWNER_ID, False, None, 200),
        (LOCAL_OWNER_ID, True, None, 403),
        (LOCAL_OWNER_ID, False, "Bearer forged", 401),
        (UUID("00000000-0000-0000-0000-000000000099"), False, None, 403),
    ],
)
async def test_local_adapter_is_explicit_and_cannot_be_overridden(
    database, identity, remote, authorization, status
):
    app = create_app(
        Settings(
            _env_file=None,
            database_url=database.url.render_as_string(hide_password=False),
            local_user_id=identity,
            scheduler_enabled=False,
        )
    )
    headers = {"x-user-id": str(LOCAL_OWNER_ID), "x-role": "admin", "x-forwarded-for": "127.0.0.1"}
    if authorization:
        headers["Authorization"] = authorization
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app, client=("198.51.100.1" if remote else "127.0.0.1", 123))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/me?user_id={LOCAL_OWNER_ID}", headers=headers)
            assert response.status_code == status
            assert (await client.get("/api/health")).status_code == 200


def test_user_deletion_removes_only_personal_data_and_reader_is_default(database):
    with Session(database) as session, session.begin():
        user = AppUser(display_name="Reader")
        source = Source(name="Shared", feed_url="https://example.org/feed")
        session.add_all([user, source])
        session.flush()
        assert user.role == "reader"
        assert user.active is False
        article = Article(source_id=source.id, url="https://example.org/a", title="Shared")
        session.add(article)
        session.flush()
        session.add_all(
            [
                Subscription(user_id=user.id, source_id=source.id),
                ArticleReadState(user_id=user.id, article_id=article.id),
                ArticleReadState(user_id=LOCAL_OWNER_ID, article_id=article.id),
            ]
        )
        user_id = user.id
    with Session(database) as session, session.begin():
        session.execute(delete(AppUser).where(AppUser.id == user_id))
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Subscription)) == 0
        assert session.scalar(select(func.count()).select_from(ArticleReadState)) == 1
        assert session.scalar(select(func.count()).select_from(Article)) == 1
        assert session.scalar(select(func.count()).select_from(Source)) == 1


@pytest.mark.parametrize("values", [{"role": "owner"}, {"display_name": " "}])
def test_user_constraints(database, values):
    with Session(database) as session:
        session.add(AppUser(**({"display_name": "Reader"} | values)))
        with pytest.raises(IntegrityError):
            session.commit()


def test_0003_preserves_owner_read_flags_sources_and_history(migration_config):
    command.upgrade(migration_config, "0002")
    engine = create_database_engine(migration_config.get_main_option("sqlalchemy.url"))
    try:
        with engine.begin() as connection:
            if engine.dialect.name == "postgresql":
                # New tables can inherit project-wide grants, even in a private schema.
                roles = connection.exec_driver_sql(
                    "SELECT rolname FROM pg_roles "
                    "WHERE rolname IN ('anon', 'authenticated', 'service_role')"
                ).scalars()
                for role in ["PUBLIC", *roles]:
                    connection.exec_driver_sql(
                        f"ALTER DEFAULT PRIVILEGES IN SCHEMA tnr GRANT ALL ON TABLES TO {role}"
                    )
            connection.exec_driver_sql(
                "UPDATE categories SET name = 'Existing category' WHERE id = 1"
            )
            connection.exec_driver_sql("""
                INSERT INTO sources (id, name, feed_url, category_id, enabled, created_at)
                VALUES (50, 'Existing', 'https://example.org/feed', 1, false, '2026-01-01 00:00:00')
            """)
            connection.exec_driver_sql("""
                INSERT INTO articles (id, source_id, url, title, fetched_at, is_read)
                VALUES (70, 50, 'https://example.org/read', 'Read', '2026-01-01 00:00:00', true),
                       (71, 50, 'https://example.org/unread', 'Unread',
                        '2026-01-01 00:00:00', false)
            """)
            connection.exec_driver_sql(
                "INSERT INTO collection_runs (source_id, started_at) "
                "VALUES (50, '2026-01-01 00:00:00')"
            )
        command.upgrade(migration_config, "head")
        if engine.dialect.name == "postgresql":
            with engine.connect() as connection:
                assert (
                    connection.exec_driver_sql("""
                    SELECT count(*) FROM pg_class c
                    JOIN pg_namespace n ON c.relnamespace = n.oid,
                    aclexplode(c.relacl) a
                    WHERE n.nspname = 'tnr'
                      AND c.relname IN ('app_users', 'subscriptions', 'article_read_states')
                      AND (a.grantee = 0 OR a.grantee IN (
                        SELECT oid FROM pg_roles
                        WHERE rolname IN ('anon', 'authenticated', 'service_role')
                      ))
                """).scalar_one()
                    == 0
                )
        with Session(engine) as session:
            assert session.get(AppUser, LOCAL_OWNER_ID).role == "admin"
            assert session.get(Source, 50).enabled is False
            assert session.get(Category, 1).name == "Existing category"
            assert session.get(Subscription, (LOCAL_OWNER_ID, 50)) is not None
            assert session.get(ArticleReadState, (LOCAL_OWNER_ID, 70)) is not None
            assert session.get(ArticleReadState, (LOCAL_OWNER_ID, 71)) is None
            assert session.scalar(select(func.count()).select_from(CollectionRun)) == 1
            other = AppUser(display_name="New reader")
            session.add(other)
            session.commit()
            assert session.get(ArticleReadState, (other.id, 70)) is None
            session.execute(delete(Subscription).where(Subscription.user_id == LOCAL_OWNER_ID))
            session.commit()
        assert "is_read" not in {
            column["name"] for column in inspect(engine).get_columns("articles")
        }
        command.upgrade(migration_config, "head")
        with Session(engine) as session:
            assert session.get(Subscription, (LOCAL_OWNER_ID, 50)) is None
        command.check(migration_config)
        command.downgrade(migration_config, "0002")
        with engine.connect() as connection:
            assert connection.execute(text("SELECT is_read FROM articles WHERE id=70")).scalar_one()
            assert not connection.execute(
                text("SELECT is_read FROM articles WHERE id=71")
            ).scalar_one()
    finally:
        engine.dispose()
