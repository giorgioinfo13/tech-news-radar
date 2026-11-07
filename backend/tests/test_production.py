"""Deployment boundaries without network access or the operator's database."""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.access import delete_reader, invite_reader, link_owner, set_access
from app.config import Settings
from app.main import create_app
from app.models import LOCAL_OWNER_ID, AppUser, Article, ArticleReadState, Source, Subscription

PRODUCTION = {
    "environment": "production",
    "docs_enabled": False,
    "scheduler_enabled": False,
    "supabase_url": "https://example.supabase.co",
    "database_url": (
        "postgresql://tnr_app.example:private-test-password@pooler.example.org:5432/postgres"
        "?sslmode=verify-full&sslrootcert=/etc/secrets/supabase-ca.crt"
    ),
}


@pytest.mark.parametrize(
    "overrides",
    [
        {"local_user_id": LOCAL_OWNER_ID},
        {"supabase_url": None},
        {"docs_enabled": True},
        {"database_url": "sqlite:///data/news.db"},
        {"database_url": PRODUCTION["database_url"].replace("tnr_app.example", "postgres")},
        {"database_url": PRODUCTION["database_url"].replace("verify-full", "require")},
        {"database_url": "postgresql://tnr_app:private-test-password@127.0.0.1/db?sslmode=disable"},
        {"database_url": "not-a-url"},
        {"database_url": "postgresql://tnr_app:private-test-password@pooler.example.org/db"},
    ],
)
def test_unsafe_production_settings_fail_without_credentials(overrides):
    with pytest.raises((ValidationError, ValueError)) as error:
        Settings(_env_file=None, **(PRODUCTION | overrides))
    assert "private-test-password" not in str(error.value)


def test_web_service_rejects_operator_credentials():
    config = Settings(_env_file=None, **PRODUCTION, migration_database_url="private-operator-url")
    with pytest.raises(ValueError, match="operator database credentials"):
        create_app(config)


@pytest.mark.anyio
async def test_production_health_and_denials_need_no_database_or_cors(monkeypatch):
    import psycopg

    def forbidden(*args, **kwargs):
        pytest.fail("This check must not connect to any database")

    monkeypatch.setattr(psycopg, "connect", forbidden)
    app = create_app(Settings(_env_file=None, **PRODUCTION))
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://api.test"
        ) as client:
            for path, code in (("/api/health", 200), ("/api/me", 401), ("/docs", 404)):
                response = await client.get(path, headers={"Origin": "https://untrusted.test"})
                assert response.status_code == code
                assert response.headers["Cache-Control"] == "private, no-store"
                assert response.headers["CDN-Cache-Control"] == "no-store"
                assert response.headers["Vercel-CDN-Cache-Control"] == "no-store"
                assert "Access-Control-Allow-Origin" not in response.headers
            assert (await client.post("/api/internal/collect")).status_code == 404


@pytest.mark.anyio
async def test_authenticated_responses_are_private(client):
    for path in ("/api/me", "/api/articles", "/api/subscriptions"):
        response = await client.get(path)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "private, no-store"
        assert response.headers["Vercel-CDN-Cache-Control"] == "no-store"


def test_deleting_revoked_reader_removes_only_their_personal_data(database):
    subject = uuid4()
    with Session(database) as session, session.begin():
        reader_id = invite_reader(session, subject, "Reader")
        source = Source(name="Test", feed_url="https://example.org/feed")
        session.add(source)
        session.flush()
        article = Article(source_id=source.id, title="Test", url="https://example.org/news")
        session.add(article)
        session.flush()
        for user_id in (reader_id, LOCAL_OWNER_ID):
            session.add(Subscription(user_id=user_id, source_id=source.id))
            session.add(ArticleReadState(user_id=user_id, article_id=article.id))
    with Session(database) as session, session.begin():
        set_access(session, subject, active=False)
        assert delete_reader(session, subject) == reader_id
    with Session(database) as session:
        assert session.get(AppUser, reader_id) is None
        assert session.get(AppUser, LOCAL_OWNER_ID) is not None
        for model in (Source, Article, Subscription, ArticleReadState):
            assert session.scalar(select(func.count()).select_from(model)) == 1
        assert session.scalar(select(Subscription.user_id)) == LOCAL_OWNER_ID
        assert session.scalar(select(ArticleReadState.user_id)) == LOCAL_OWNER_ID


@pytest.mark.parametrize("kind", ["active-reader", "owner", "missing"])
def test_delete_reader_refuses_active_users_owner_and_missing_identity(database, kind):
    subject = uuid4()
    with Session(database) as session, session.begin():
        if kind == "active-reader":
            invite_reader(session, subject, "Active")
        elif kind == "owner":
            link_owner(session, subject)
            set_access(session, subject, active=False)
        with pytest.raises(ValueError, match="revoked reader"):
            delete_reader(session, subject)
