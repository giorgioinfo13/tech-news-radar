from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_multiuser import people as people_fixture

from app.api import personal
from app.models import AppUser

people = people_fixture


@pytest.mark.anyio
async def test_usage_authorization_counts_and_throttle(people, database, monkeypatch):
    clients, ids, source, article, _ = people
    now = datetime(2026, 11, 10, 12, tzinfo=UTC)
    monkeypatch.setattr(personal, "utc_now", lambda: now)
    assert (await clients["alice"].get("/api/usage/readers")).status_code == 403
    await clients["alice"].put(f"/api/subscriptions/{source}")
    await clients["alice"].patch(f"/api/articles/{article}", json={"is_read": True})
    assert (await clients["alice"].get("/api/me")).status_code == 200
    monkeypatch.setattr(personal, "utc_now", lambda: now + timedelta(minutes=14))
    assert (await clients["alice"].get("/api/me")).status_code == 200
    response = await clients["admin"].get("/api/usage/readers")
    assert response.headers["Cache-Control"] == "private, no-store"
    rows = {row["display_name"]: row for row in response.json()["items"]}
    assert set(rows) == {"alice", "bob"}
    assert rows["alice"]["last_seen_at"] == now.isoformat().replace("+00:00", "Z")
    assert rows["alice"]["followed_sources"] == 1
    assert rows["alice"]["read_articles"] == 1
    assert rows["alice"]["last_read_at"] is not None
    assert rows["bob"]["last_seen_at"] is None
    assert rows["bob"]["read_articles"] == 0
    monkeypatch.setattr(personal, "utc_now", lambda: now + timedelta(minutes=15))
    await clients["alice"].get("/api/me")
    with Session(database) as session, session.begin():
        assert session.get(AppUser, ids["alice"]).last_seen_at == now + timedelta(minutes=15)
        session.get(AppUser, ids["alice"]).active = False
    assert (await clients["alice"].get("/api/me")).status_code == 403
    assert (await clients["alice"].get("/api/usage/readers")).status_code == 403
    assert (await clients["admin"].get("/api/usage/readers")).json()["total"] == 1


@pytest.mark.anyio
async def test_optional_usage_failure_does_not_block_access(people, monkeypatch):
    clients, _, _, _, _ = people

    def failed_commit(self):
        raise SQLAlchemyError("telemetry unavailable")

    monkeypatch.setattr(Session, "commit", failed_commit)
    assert (await clients["alice"].get("/api/me")).status_code == 200


def test_usage_migration_roundtrip(database, migration_config):
    command.downgrade(migration_config, "0011")
    assert "last_seen_at" not in {c["name"] for c in inspect(database).get_columns("app_users")}
    command.upgrade(migration_config, "head")
    command.check(migration_config)
