from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import uuid4

import pytest
from alembic import command
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_identity
from app.api.proposals import approve_proposal, create_proposal
from app.collection.download import Download, FeedDownloader
from app.collection.service import Collector
from app.config import Settings
from app.main import create_app
from app.models import LOCAL_OWNER_ID, AppUser, Category, Source, SourceProposal, Subscription
from app.schemas import ProposalApprove, ProposalCreate

RSS = b'<rss version="2.0"><channel><title>News</title></channel></rss>'


@pytest.fixture
async def proposal_app(database, monkeypatch):
    ids = [uuid4(), uuid4()]
    with Session(database) as session, session.begin():
        session.add_all(
            [AppUser(id=id, display_name=f"Reader {i}", active=True) for i, id in enumerate(ids)]
        )
    app = create_app(
        Settings(
            _env_file=None,
            database_url=database.url.render_as_string(hide_password=False),
            local_user_id=LOCAL_OWNER_ID,
            scheduler_enabled=False,
        )
    )
    identity = {"id": ids[0]}
    app.dependency_overrides[get_identity] = lambda: identity["id"]
    downloads = []

    def fetch(self, url, *args):
        downloads.append(url)
        return Download(RSS, url)

    monkeypatch.setattr(FeedDownloader, "fetch", fetch)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, identity, ids, downloads, app


@pytest.mark.anyio
async def test_reader_isolation_limits_cancel_and_permissions(proposal_app, database):
    client, identity, ids, downloads, _ = proposal_app
    result = await client.post("/api/proposals", json={"name": " Only a name "})
    assert result.status_code == 201
    proposal = result.json()
    assert proposal["name"] == "Only a name" and proposal["url"] is None
    assert downloads == []
    assert (await client.post("/api/proposals", json={"name": "ONLY A NAME"})).status_code == 409
    identity["id"] = ids[1]
    assert (await client.get("/api/proposals")).json()["total"] == 0
    assert (await client.post(f"/api/proposals/{proposal['id']}/cancel")).status_code == 404
    assert (
        await client.post(f"/api/proposals/{proposal['id']}/approve", json={"source_id": 1})
    ).status_code == 403
    assert (
        await client.post(f"/api/proposals/{proposal['id']}/reject", json={"reason": "No"})
    ).status_code == 403
    identity["id"] = ids[0]
    for i in range(4):
        assert (await client.post("/api/proposals", json={"name": f"Other {i}"})).status_code == 201
    assert (await client.post("/api/proposals", json={"name": "Sixth"})).status_code == 409
    path = f"/api/proposals/{proposal['id']}/cancel"
    assert (await client.post(path)).json()["status"] == "cancelled"
    assert (await client.post(path)).status_code == 200
    assert (await client.post("/api/proposals", json={"name": "Sixth"})).status_code == 201
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Source)) == 0


@pytest.mark.anyio
async def test_approval_is_atomic_repeat_safe_and_personal(proposal_app, database):
    client, identity, ids, downloads, _ = proposal_app
    proposal = (
        await client.post("/api/proposals", json={"name": "News", "follow_on_approval": True})
    ).json()
    identity["id"] = LOCAL_OWNER_ID
    path = f"/api/proposals/{proposal['id']}/approve"
    assert (await client.post(path, json={"name": "Corrected"})).status_code == 422
    body = {"name": "Corrected", "feed_url": "https://example.org/feed", "category_id": 1}
    result = await client.post(path, json=body)
    assert result.status_code == 200, result.text
    assert result.json()["approved_name"] == "Corrected"
    assert (await client.post(path, json=body)).json() == result.json()
    assert downloads == ["https://example.org/feed"]
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Source)) == 1
        subscription = session.scalar(select(Subscription))
        assert subscription.user_id == ids[0]
        assert session.scalar(select(func.count()).select_from(Subscription)) == 1
        stored = session.get(SourceProposal, proposal["id"])
        assert stored.decided_by == LOCAL_OWNER_ID and stored.decided_at is not None
    identity["id"] = ids[0]
    assert (await client.post(f"/api/proposals/{proposal['id']}/cancel")).status_code == 409
    assert (await client.get("/api/proposals")).json()["items"][0]["status"] == "approved"


@pytest.mark.anyio
async def test_existing_source_revocation_category_removal_and_rejection(proposal_app, database):
    client, identity, ids, downloads, _ = proposal_app
    with Session(database) as session, session.begin():
        source = Source(name="Existing", feed_url="https://example.org/feed", enabled=False)
        session.add(source)
        session.flush()
        source_id = source.id
    first = (await client.post("/api/proposals", json={"name": "First", "category_id": 1})).json()
    with Session(database) as session, session.begin():
        session.delete(session.get(Category, 1))
    identity["id"] = LOCAL_OWNER_ID
    result = await client.post(
        f"/api/proposals/{first['id']}/approve", json={"source_id": source_id}
    )
    assert result.status_code == 200
    assert result.json()["category_id"] is None
    assert downloads == []
    identity["id"] = ids[0]
    second = (
        await client.post("/api/proposals", json={"name": "Second", "follow_on_approval": True})
    ).json()
    with Session(database) as session, session.begin():
        session.get(AppUser, ids[0]).active = False
    assert (await client.get("/api/proposals")).status_code == 403
    identity["id"] = LOCAL_OWNER_ID
    path = f"/api/proposals/{second['id']}"
    assert (await client.post(path + "/approve", json={"source_id": source_id})).status_code == 409
    assert (await client.post(path + "/reject", json={"reason": " "})).status_code == 422
    result = await client.post(path + "/reject", json={"reason": "No accessible feed"})
    assert result.json()["status"] == "rejected"
    assert (
        await client.post(path + "/reject", json={"reason": "No accessible feed"})
    ).status_code == 200
    with Session(database) as session, session.begin():
        assert session.scalar(select(func.count()).select_from(Subscription)) == 0
        assert session.get(Source, source_id).enabled is False
        session.get(AppUser, ids[0]).active = True
    identity["id"] = ids[0]
    assert (await client.get("/api/proposals")).json()["items"][0]["reason"] == "No accessible feed"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "data",
    [
        {"name": " "},
        {"name": "x" * 201},
        {"name": "News", "note": "x" * 501},
        {"name": "News", "url": "file:///tmp/private"},
        {"name": "News", "url": "https://u:p@example.org"},
        {"name": "News", "url": "https://example.org:8080/feed"},
        {"name": "News", "status": "approved"},
        {"name": "News", "user_id": str(LOCAL_OWNER_ID)},
    ],
)
async def test_input_boundaries(proposal_app, data):
    client, _, _, downloads, _ = proposal_app
    assert (await client.post("/api/proposals", json=data)).status_code == 422
    assert downloads == []


@pytest.mark.anyio
async def test_invalid_feed_and_removed_category_leave_no_side_effects(
    proposal_app, database, monkeypatch
):
    client, identity, _, _, _ = proposal_app
    proposal = (await client.post("/api/proposals", json={"name": "News"})).json()
    identity["id"] = LOCAL_OWNER_ID
    monkeypatch.setattr(FeedDownloader, "fetch", lambda self, url: Download(b"<html/>", url))
    path = f"/api/proposals/{proposal['id']}/approve"
    body = {"name": "News", "feed_url": "https://example.org/feed"}
    assert (await client.post(path, json=body)).status_code == 422
    monkeypatch.setattr(FeedDownloader, "fetch", lambda self, url: Download(RSS, url))
    assert (await client.post(path, json={**body, "category_id": 999})).status_code == 404
    with Session(database) as session:
        assert session.get(SourceProposal, proposal["id"]).status == "pending"
        assert session.scalar(select(func.count()).select_from(Source)) == 0


def test_concurrent_submissions_cannot_exceed_limit(database):
    barrier = Barrier(8)

    def submit(i):
        with Session(database) as session:
            user = session.get(AppUser, LOCAL_OWNER_ID)
            session.expunge(user)
            session.rollback()
            barrier.wait()
            try:
                create_proposal(ProposalCreate(name=f"News {i}"), user, session)
                return 201
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(submit, range(8)))
    assert results.count(201) == 5 and results.count(409) == 3


def test_concurrent_approval_creates_one_source_and_subscription(database, monkeypatch):
    with Session(database) as session:
        proposal = create_proposal(
            ProposalCreate(name="News", follow_on_approval=True),
            session.get(AppUser, LOCAL_OWNER_ID),
            session,
        )
        proposal_id = proposal.id
    barrier = Barrier(2)

    def fetch(self, url):
        barrier.wait()
        return Download(RSS, url)

    monkeypatch.setattr(FeedDownloader, "fetch", fetch)

    def approve(_):
        collector = Collector(database, Settings(_env_file=None))
        with Session(database) as session:
            result = approve_proposal(
                proposal_id,
                ProposalApprove(name="News", feed_url="https://example.org/feed"),
                session.get(AppUser, LOCAL_OWNER_ID),
                session,
                collector,
            )
            return result.source_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(approve, range(2)))
    assert results[0] == results[1]
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Source)) == 1
        assert session.scalar(select(func.count()).select_from(Subscription)) == 1


@pytest.mark.anyio
async def test_cancellation_during_validation_wins(proposal_app, database, monkeypatch):
    import asyncio

    client, identity, ids, _, _ = proposal_app
    proposal = (await client.post("/api/proposals", json={"name": "News"})).json()
    started, release = Event(), Event()

    def fetch(self, url):
        started.set()
        assert release.wait(5)
        return Download(RSS, url)

    monkeypatch.setattr(FeedDownloader, "fetch", fetch)
    identity["id"] = LOCAL_OWNER_ID
    task = asyncio.create_task(
        client.post(
            f"/api/proposals/{proposal['id']}/approve",
            json={"name": "News", "feed_url": "https://example.org/feed"},
        )
    )
    assert await asyncio.to_thread(started.wait, 5)
    identity["id"] = ids[0]
    assert (await client.post(f"/api/proposals/{proposal['id']}/cancel")).status_code == 200
    release.set()
    assert (await task).status_code == 409
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Source)) == 0


def test_proposal_migration_preserves_prior_data(database, migration_config):
    from app.transfer import TABLES, read_rows

    command.downgrade(migration_config, "0005")
    tables = [table for table in TABLES if table.name != "source_proposals"]
    with database.connect() as connection:
        before = {table.name: read_rows(connection, table) for table in tables}
    command.upgrade(migration_config, "head")
    command.check(migration_config)
    with database.connect() as connection:
        assert before == {table.name: read_rows(connection, table) for table in tables}


@pytest.mark.anyio
async def test_existing_url_links_without_fetch_or_duplicate_subscription(proposal_app, database):
    client, identity, ids, downloads, _ = proposal_app
    with Session(database) as session, session.begin():
        source = Source(name="Original", feed_url="https://example.org/existing")
        session.add(source)
        session.flush()
        source_id = source.id
        session.add(Subscription(user_id=ids[0], source_id=source_id))
    proposal = (
        await client.post(
            "/api/proposals", json={"name": "Another name", "follow_on_approval": True}
        )
    ).json()
    identity["id"] = LOCAL_OWNER_ID
    result = await client.post(
        f"/api/proposals/{proposal['id']}/approve",
        json={"name": "Different", "feed_url": "https://example.org/existing"},
    )
    assert result.status_code == 200
    assert result.json()["approved_name"] == "Original"
    assert downloads == []
    with Session(database) as session, session.begin():
        assert session.scalar(select(func.count()).select_from(Subscription)) == 1
        session.delete(session.get(Source, source_id))
    identity["id"] = ids[0]
    result = (await client.get("/api/proposals")).json()["items"][0]
    assert result["source_id"] is None and result["approved_name"] == "Original"


@pytest.mark.anyio
async def test_revocation_during_validation_rolls_back_approval(
    proposal_app, database, monkeypatch
):
    client, identity, ids, _, _ = proposal_app
    proposal = (
        await client.post("/api/proposals", json={"name": "News", "follow_on_approval": True})
    ).json()

    def revoke(self, url):
        with Session(database) as session, session.begin():
            session.get(AppUser, ids[0]).active = False
        return Download(RSS, url)

    monkeypatch.setattr(FeedDownloader, "fetch", revoke)
    identity["id"] = LOCAL_OWNER_ID
    result = await client.post(
        f"/api/proposals/{proposal['id']}/approve",
        json={"name": "News", "feed_url": "https://example.org/new"},
    )
    assert result.status_code == 409
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Source)) == 0
        assert session.scalar(select(func.count()).select_from(Subscription)) == 0
        assert session.get(SourceProposal, proposal["id"]).status == "pending"


@pytest.mark.anyio
async def test_proposals_require_identity_on_direct_api_calls(database):
    app = create_app(
        Settings(
            _env_file=None,
            database_url=database.url.render_as_string(hide_password=False),
            scheduler_enabled=False,
        )
    )
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for method, path, body in [
                ("GET", "/api/proposals", None),
                ("POST", "/api/proposals", {"name": "Test"}),
                ("POST", "/api/proposals/1/cancel", None),
                ("POST", "/api/proposals/1/reject", {"reason": "Test"}),
                ("POST", "/api/proposals/1/approve", {"source_id": 1}),
            ]:
                assert (await client.request(method, path, json=body)).status_code == 401
