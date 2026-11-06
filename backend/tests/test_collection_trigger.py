import asyncio
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collection.download import FeedDownloader
from app.collection.service import RefreshRejected
from app.config import Settings
from app.main import create_app
from app.models import CollectionRun, Source

SECRET = "test-only-collection-secret-000000000000"
AUTH = {"Authorization": "Bearer " + SECRET}
PATH = "/api/internal/collect"
RSS = (Path(__file__).parent / "fixtures/rss.xml").read_bytes()


@pytest.fixture
async def trigger(database, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("app.collection.trigger.monotonic", lambda: clock[0])
    monkeypatch.setattr("app.collection.service.utc_now", lambda: datetime(2026, 11, 6, tzinfo=UTC))
    settings = Settings(
        _env_file=None,
        database_url=database.url.render_as_string(hide_password=False),
        scheduler_enabled=False,
        collection_trigger_secret=SECRET,
    )
    app = create_app(settings)
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, stream=httpx.ByteStream(RSS))

    async with app.router.lifespan_context(app):
        app.state.collector.downloader = FeedDownloader(
            settings,
            resolver=lambda host, port: "93.184.215.14",
            transport=httpx.MockTransport(respond),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield app, client, requests, clock


def add_sources(database, count=1):
    with Session(database) as session:
        session.add_all(
            Source(name=f"Source {i}", feed_url=f"https://example.org/{i}") for i in range(count)
        )
        session.commit()


@pytest.mark.anyio
async def test_trigger_disabled_by_default(client):
    assert (await client.post(PATH, headers=AUTH)).status_code == 404


@pytest.mark.anyio
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong"},
        {"Authorization": "Basic " + SECRET},
        {"Authorization": "Bearer fake.google.jwt"},
        [("Authorization", "Bearer " + SECRET), ("Authorization", "Bearer " + SECRET)],
    ],
)
async def test_auth_rejected_before_database_access(trigger, headers, monkeypatch):
    app, client, requests, _ = trigger
    monkeypatch.setattr(app.state.collection_trigger, "run", lambda: pytest.fail("Scan reached"))
    response = await client.post(PATH, headers=headers)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert SECRET not in response.text
    assert requests == []


@pytest.mark.anyio
async def test_no_query_auth_no_get_and_no_user_privileges(trigger):
    _, client, requests, _ = trigger
    assert (await client.post(PATH, params={"token": SECRET})).status_code == 401
    assert (await client.get(PATH, headers=AUTH)).status_code == 405
    assert (await client.get("/api/me", headers=AUTH)).status_code == 401
    assert PATH not in (await client.get("/openapi.json")).json()["paths"]
    assert requests == []


@pytest.mark.anyio
async def test_scan_cooldown_and_restart_preserve_due_times(trigger, database, monkeypatch):
    app, client, requests, clock = trigger
    add_sources(database)
    response = await client.post(PATH, headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {"collected": 1, "failed": 0, "skipped": 0, "deferred": False}
    assert response.headers["cache-control"] == "no-store"
    limited = await client.post(PATH, headers=AUTH)
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "300"
    clock[0] += 300
    assert (await client.post(PATH, headers=AUTH)).json()["skipped"] == 1
    assert len(requests) == 1

    monkeypatch.setattr(FeedDownloader, "fetch", lambda *args: pytest.fail("Not due after restart"))
    restarted = create_app(app.state.settings)
    async with restarted.router.lifespan_context(restarted):
        assert restarted.state.scheduler is None
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=restarted), base_url="http://test"
        ) as other:
            assert (await other.post(PATH, headers=AUTH)).json()["skipped"] == 1
    with Session(database) as session:
        assert len(session.scalars(select(CollectionRun)).all()) == 1


@pytest.mark.anyio
async def test_budget_defers_remaining_sources_without_starvation(trigger, database):
    _, client, requests, clock = trigger
    add_sources(database, 27)
    first = (await client.post(PATH, headers=AUTH)).json()
    assert first == {"collected": 25, "failed": 0, "skipped": 0, "deferred": True}
    clock[0] += 300
    second = (await client.post(PATH, headers=AUTH)).json()
    assert second == {"collected": 2, "failed": 0, "skipped": 25, "deferred": False}
    assert len(requests) == 27


@pytest.mark.anyio
async def test_failed_feed_is_reported_without_blocking_next_feed(trigger, database):
    app, client, _, clock = trigger
    add_sources(database, 2)
    requests = []

    def respond(request):
        requests.append(request)
        status = 503 if len(requests) == 1 else 200
        return httpx.Response(status, stream=httpx.ByteStream(RSS))

    app.state.collector.downloader = FeedDownloader(
        app.state.settings,
        resolver=lambda host, port: "93.184.215.14",
        transport=httpx.MockTransport(respond),
    )
    assert (await client.post(PATH, headers=AUTH)).json() == {
        "collected": 1,
        "failed": 1,
        "skipped": 0,
        "deferred": False,
    }
    clock[0] += 300
    assert (await client.post(PATH, headers=AUTH)).json()["skipped"] == 2
    assert len(requests) == 2


@pytest.mark.anyio
async def test_time_budget_finishes_active_feed_then_defers(trigger, database, monkeypatch):
    app, client, requests, _ = trigger
    add_sources(database, 2)
    now = [0.0]
    monkeypatch.setattr("app.collection.scheduler.monotonic", lambda: now[0])
    original = app.state.collector.downloader.fetch

    def fetch(*args):
        now[0] = 241
        return original(*args)

    monkeypatch.setattr(app.state.collector.downloader, "fetch", fetch)
    assert (await client.post(PATH, headers=AUTH)).json() == {
        "collected": 1,
        "failed": 0,
        "skipped": 0,
        "deferred": True,
    }
    assert len(requests) == 1


@pytest.mark.anyio
async def test_overlapping_scan_and_manual_refresh_rejected_health_responsive(
    trigger, database, monkeypatch
):
    app, client, _, _ = trigger
    add_sources(database)
    entered, release = Event(), Event()
    collector = app.state.collector
    original = collector.downloader.fetch

    def fetch(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(collector.downloader, "fetch", fetch)
    task = asyncio.create_task(client.post(PATH, headers=AUTH))
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        assert (await client.post(PATH, headers=AUTH)).status_code == 409
        assert (await client.get("/api/health")).status_code == 200
        with pytest.raises(RefreshRejected) as rejected:
            collector.refresh(1)
        assert rejected.value.status_code == 409
        with pytest.raises(RefreshRejected):
            with collector.exclusive():
                pytest.fail("Source writes must share the collector lock")
    finally:
        release.set()
        response = await asyncio.wait_for(task, 5)
    assert response.json()["collected"] == 1


@pytest.mark.anyio
async def test_busy_collector_defers_scan_and_failed_scan_is_throttled(
    trigger, database, monkeypatch, caplog
):
    app, client, requests, clock = trigger
    add_sources(database)
    with app.state.collector.exclusive():
        assert (await client.post(PATH, headers=AUTH)).json()["deferred"] is True
    assert requests == []
    clock[0] += 300

    def fail(**kwargs):
        raise RuntimeError("private database credential")

    monkeypatch.setattr(app.state.collection_trigger.scheduler, "run_once", fail)
    response = await client.post(PATH, headers=AUTH)
    assert response.status_code == 503
    assert "private database credential" not in response.text + caplog.text
    assert (await client.post(PATH, headers=AUTH)).status_code == 429


@pytest.mark.anyio
async def test_shutdown_stops_after_active_feed_and_waits(trigger, database, monkeypatch):
    app, client, requests, _ = trigger
    add_sources(database, 2)
    entered, release = Event(), Event()
    original = app.state.collector.downloader.fetch

    def fetch(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(app.state.collector.downloader, "fetch", fetch)
    task = asyncio.create_task(client.post(PATH, headers=AUTH))
    stop = None
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        stop = asyncio.create_task(asyncio.to_thread(app.state.collection_trigger.stop))
        assert await asyncio.to_thread(app.state.collection_trigger.scheduler._stop.wait, 3)
        assert not stop.done()
    finally:
        release.set()
        result = await asyncio.wait_for(task, 5)
        if stop:
            await asyncio.wait_for(stop, 5)
    assert result.json()["deferred"] is True
    assert len(requests) == 1
    assert (await client.post(PATH, headers=AUTH)).status_code == 503


@pytest.mark.parametrize("value", ["", "short", "x" * 129, "secret with spaces" * 3, "é" * 32])
def test_invalid_secrets_rejected_without_disclosure(value):
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, scheduler_enabled=False, collection_trigger_secret=value)
    if value:
        assert value not in str(error.value)


def test_mutually_exclusive_timers_and_secret_redaction():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, scheduler_enabled=True, collection_trigger_secret=SECRET)
    settings = Settings(_env_file=None, scheduler_enabled=False, collection_trigger_secret=SECRET)
    assert SECRET not in repr(settings)
    assert SECRET not in settings.model_dump_json()
