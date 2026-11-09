"""RSS-only refresh contracts against migrated, temporary databases and simulated HTTP."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_identity
from app.collection.download import FeedDownloader
from app.collection.scheduler import CollectionScheduler
from app.collection.service import Collector, RefreshRejected
from app.config import Settings
from app.main import create_app
from app.models import LOCAL_OWNER_ID, AppUser, Article, CollectionRun, Source, Subscription

RSS = (Path(__file__).parent / "fixtures/rss.xml").read_bytes()


@pytest.fixture
async def news(database, monkeypatch):
    settings = Settings(
        database_url=database.url.render_as_string(hide_password=False),
        local_user_id=LOCAL_OWNER_ID,
        scheduler_enabled=False,
    )
    app = create_app(settings)
    clock = [datetime(2026, 11, 9, tzinfo=UTC)]
    monkeypatch.setattr("app.collection.service.utc_now", lambda: clock[0])
    requests, replies = [], []

    def handle(request):
        requests.append(request)
        reply = (
            replies.pop(0)
            if replies
            else httpx.Response(
                200,
                stream=httpx.ByteStream(RSS),
                headers={"etag": '"v1"', "last-modified": "Mon, 09 Nov 2026 00:00:00 GMT"},
            )
        )
        if isinstance(reply, Exception):
            raise reply
        return reply

    with Session(database) as session:
        session.add_all(
            [Source(name=str(i), feed_url=f"https://example.org/{i}") for i in range(1, 4)]
        )
        session.commit()
    async with app.router.lifespan_context(app):
        collector = app.state.collector
        collector.downloader = FeedDownloader(
            settings, resolver=lambda *args: "93.184.215.14", transport=httpx.MockTransport(handle)
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, collector, clock, requests, replies, app


pytestmark = pytest.mark.anyio


async def test_admin_refresh_conditional_dedup_cooldown_and_scheduler(news, database):
    client, collector, clock, requests, replies, _ = news
    first = (await client.post("/api/sources/refresh")).json()
    assert (first["checked"], first["added"], first["failed"]) == (3, 6, 0)
    assert (await client.post("/api/sources/refresh")).json()["skipped"] == 3
    assert (await client.post("/api/sources/1/refresh")).status_code == 429
    assert CollectionScheduler(collector, 30).run_once().collected == 0
    assert len(requests) == 3
    clock[0] += timedelta(minutes=15)
    replies.extend(
        [
            httpx.Response(304),
            httpx.Response(200, stream=httpx.ByteStream(RSS)),
            httpx.Response(304),
        ]
    )
    result = (await client.post("/api/sources/refresh")).json()
    assert (result["checked"], result["added"], result["failed"]) == (3, 0, 0)
    assert requests[-1].headers["if-none-match"] == '"v1"'
    assert requests[-1].headers["if-modified-since"].startswith("Mon, 09")
    assert all(
        request.method == "GET" and request.headers["host"] == "example.org" for request in requests
    )
    with Session(database) as session:
        assert len(session.scalars(select(Article)).all()) == 6
    clock[0] += timedelta(minutes=59)
    assert CollectionScheduler(collector, 30).run_once().collected == 0
    clock[0] += timedelta(minutes=1)
    assert CollectionScheduler(collector, 30).run_once().collected == 3


async def test_reader_scope_revoked_unknown_and_no_identity(news, database):
    client, _, _, requests, _, app = news
    reader_id = uuid4()
    with Session(database) as session:
        session.add(AppUser(id=reader_id, display_name="Reader", role="reader", active=True))
        session.flush()
        session.add(Subscription(user_id=reader_id, source_id=2))
        session.commit()
    app.dependency_overrides[get_identity] = lambda: reader_id
    assert (await client.post("/api/sources/1/refresh")).status_code == 403
    response = await client.post("/api/sources/refresh")
    assert response.status_code == 200
    assert response.json()["checked"] == 1
    assert [request.url.path for request in requests] == ["/2"]
    with Session(database) as session:
        session.get(AppUser, reader_id).active = False
        session.commit()
    assert (await client.post("/api/sources/refresh")).status_code == 403
    app.dependency_overrides[get_identity] = lambda: uuid4()
    assert (await client.post("/api/sources/refresh")).status_code == 403
    app.dependency_overrides.clear()
    app.state.settings.local_user_id = None
    assert (await client.post("/api/sources/refresh")).status_code == 401
    assert len(requests) == 1


async def test_recent_disabled_and_backoff_do_not_block_other_sources(news, database):
    client, _, clock, requests, _, _ = news
    with Session(database) as session:
        session.get(Source, 1).enabled = False
        second = session.get(Source, 2)
        second.last_checked_at = clock[0] - timedelta(minutes=20)
        second.consecutive_failures = 7
        session.commit()
    result = (await client.post("/api/sources/refresh")).json()
    assert (result["checked"], result["skipped"], result["retry_after"]) == (1, 2, 2400)
    assert [request.url.path for request in requests] == ["/3"]


async def test_partial_failures_and_no_ai_dispatch(news, database, monkeypatch):
    client, _, _, _, replies, app = news
    # A live AI configuration must not matter: any unexpected provider HTTP is denied
    # globally by conftest, and the only injected transport belongs to the RSS downloader.
    from app.models import AIBriefBudget, AIBriefJob

    def no_ai(*args, **kwargs):
        pytest.fail("RSS refresh must not invoke the AI service")

    monkeypatch.setattr(app.state.briefs, "reserve", no_ai)
    app.state.settings.ai_briefs_enabled = True
    app.state.settings.ai_digest_enabled = True
    replies.extend([httpx.ReadTimeout("secret"), httpx.Response(503)])
    result = (await client.post("/api/sources/refresh")).json()
    assert (result["checked"], result["failed"], result["added"]) == (3, 2, 2)
    with Session(database) as session:
        assert [
            run.status for run in session.scalars(select(CollectionRun).order_by(CollectionRun.id))
        ] == ["error", "error", "success"]
        assert all(
            "secret" not in (source.last_error or "") for source in session.scalars(select(Source))
        )
        assert session.scalars(select(AIBriefBudget)).all() == []
        assert session.scalars(select(AIBriefJob)).all() == []


async def test_source_count_and_time_limits_leave_untouched_sources_eligible(
    news, database, monkeypatch
):
    client, _, clock, requests, _, _ = news
    with Session(database) as session:
        session.add_all(
            [Source(name=str(i), feed_url=f"https://example.org/{i}") for i in range(4, 14)]
        )
        session.commit()
    first = (await client.post("/api/sources/refresh")).json()
    assert (first["checked"], first["deferred"]) == (10, 3)
    second = (await client.post("/api/sources/refresh")).json()
    assert (second["checked"], second["skipped"], second["deferred"]) == (3, 10, 0)
    assert len(requests) == 13
    clock[0] += timedelta(minutes=15)
    monkeypatch.setattr("app.collection.service.MANUAL_MAX_SECONDS", 0)
    result = (await client.post("/api/sources/refresh")).json()
    assert (result["checked"], result["deferred"]) == (0, 13)
    assert len(requests) == 13


async def test_parallel_users_single_refresh_scheduler_and_second_collector_share_gate(
    news, database
):
    client, collector, _, requests, _, _ = news
    started, release = Event(), Event()
    original = collector.downloader.fetch

    def blocked(*args, **kwargs):
        started.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    collector.downloader.fetch = blocked
    task = asyncio.create_task(client.post("/api/sources/refresh"))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        assert (await client.post("/api/sources/refresh")).status_code == 409
        assert (await client.post("/api/sources/2/refresh")).status_code == 409
        other = Collector(database, collector.settings)
        with pytest.raises(RefreshRejected) as rejected:
            other.refresh(2)
        assert rejected.value.status_code == 409
        assert CollectionScheduler(other, 30).run_once().deferred
        assert (await client.patch("/api/sources/2", json={"enabled": False})).status_code == 409
    finally:
        release.set()
    assert (await task).json()["checked"] == 3
    assert len(requests) == 3


async def test_interruption_persists_reservation_and_recovers_after_restart(news, database):
    _, collector, clock, requests, _, _ = news
    original = collector.downloader.fetch

    def interrupted(*args, **kwargs):
        raise SystemExit("simulated process interruption")

    collector.downloader.fetch = interrupted
    with pytest.raises(SystemExit):
        collector.refresh(1)
    restarted = Collector(database, collector.settings)
    restarted.downloader.fetch = original
    with pytest.raises(RefreshRejected) as rejected:
        restarted.refresh(1)
    assert rejected.value.retry_after == 900
    # Other never-checked sources are not stalled by the interrupted source.
    assert restarted.refresh_news(LOCAL_OWNER_ID).checked == 2
    clock[0] += timedelta(minutes=15)
    assert restarted.refresh(1).status == "success"
    with Session(database) as session:
        runs = session.scalars(
            select(CollectionRun).where(CollectionRun.source_id == 1).order_by(CollectionRun.id)
        ).all()
        assert [run.status for run in runs] == ["error", "success"]
    assert len(requests) == 3


async def test_revocation_during_batch_is_rechecked_before_next_download(news, database):
    client, collector, _, requests, _, _ = news
    original = collector.downloader.fetch

    def revoke(*args, **kwargs):
        result = original(*args, **kwargs)
        with Session(database) as session:
            session.get(AppUser, LOCAL_OWNER_ID).active = False
            session.commit()
        return result

    collector.downloader.fetch = revoke
    assert (await client.post("/api/sources/refresh")).status_code == 403
    assert len(requests) == 1


async def test_late_download_does_not_report_success(news, monkeypatch):
    client, collector, _, requests, _, _ = news
    tick = [0]
    monkeypatch.setattr("app.collection.service.monotonic", lambda: tick[0])
    original = collector.downloader.fetch

    def late(*args, **kwargs):
        kwargs.pop("deadline")
        result = original(*args, **kwargs)
        tick[0] = 46
        return result

    collector.downloader.fetch = late
    result = (await client.post("/api/sources/refresh")).json()
    assert (result["checked"], result["failed"], result["added"], result["deferred"]) == (
        1,
        1,
        0,
        2,
    )
    assert len(requests) == 1


async def test_single_source_url_changes_cannot_bypass_persisted_backoff(news, database):
    client, _, clock, requests, _, _ = news
    with Session(database) as session:
        source = session.get(Source, 1)
        source.last_checked_at = clock[0]
        source.consecutive_failures = 7
        session.commit()
    assert (
        await client.patch("/api/sources/1", json={"feed_url": "https://example.org/new"})
    ).status_code == 200
    result = await client.post("/api/sources/1/refresh")
    assert result.status_code == 429
    assert result.headers["retry-after"] == "3600"
    assert not requests
