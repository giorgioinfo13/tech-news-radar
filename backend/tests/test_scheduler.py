import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.collection.download import Download, FeedDownloader
from app.collection.scheduler import CollectionScheduler
from app.collection.service import Collector, RefreshRejected
from app.config import Settings
from app.main import create_app
from app.models import Article, CollectionRun, Source

RSS = (Path(__file__).parent / "fixtures/rss.xml").read_bytes()


@pytest.fixture
def setup(database, monkeypatch):
    clock = [datetime(2026, 11, 6, tzinfo=UTC)]
    monkeypatch.setattr("app.collection.service.utc_now", lambda: clock[0])
    settings = Settings(_env_file=None, scheduler_enabled=False)
    collector = Collector(database, settings)
    requests, replies = [], []

    def handle(request):
        requests.append(request)
        return replies.pop(0) if replies else httpx.Response(200, stream=httpx.ByteStream(RSS))

    collector.downloader = FeedDownloader(
        settings,
        resolver=lambda host, port: "93.184.215.14",
        transport=httpx.MockTransport(handle),
    )
    with Session(database) as session:
        source = Source(name="Test", feed_url="https://example.org/feed")
        session.add(source)
        session.commit()
        source_id = source.id
    return collector, CollectionScheduler(collector, 30), source_id, clock, requests, replies


def test_first_collection_interval_boundary_and_restart_use_persisted_dates(setup, database):
    collector, scheduler, source_id, clock, requests, replies = setup
    replies.append(httpx.Response(200, stream=httpx.ByteStream(RSS), headers={"etag": '"one"'}))
    scheduler.run_once()
    assert len(requests) == 1
    with Session(database) as session:
        article = session.scalar(select(Article).where(Article.source_id == source_id))
        article.is_read = True
        session.commit()
    clock[0] += timedelta(minutes=60) - timedelta(microseconds=1)
    # A fresh scheduler instance also respects the last completed check.
    restarted = CollectionScheduler(collector, 30)
    restarted.run_once()
    assert len(requests) == 1
    clock[0] += timedelta(microseconds=1)
    replies.append(httpx.Response(304))
    restarted.run_once()
    assert len(requests) == 2
    assert requests[-1].headers["if-none-match"] == '"one"'
    with Session(database) as session:
        runs = session.scalars(select(CollectionRun).order_by(CollectionRun.id)).all()
        assert [run.status for run in runs] == ["success", "not_modified"]
        assert session.scalar(select(Article).where(Article.is_read.is_(True))) is not None
        assert len(session.scalars(select(Article)).all()) == 2


def test_manual_refresh_postpones_automatic_collection(setup):
    collector, scheduler, source_id, clock, requests, _ = setup
    collector.refresh(source_id)
    clock[0] += timedelta(minutes=59)
    scheduler.run_once()
    assert len(requests) == 1
    clock[0] += timedelta(minutes=1)
    scheduler.run_once()
    assert len(requests) == 2


def test_disabled_deleted_and_changed_intervals_are_rechecked(setup, database):
    collector, scheduler, source_id, clock, requests, _ = setup
    with Session(database) as session:
        source = session.get(Source, source_id)
        source.enabled = False
        session.commit()
    scheduler.run_once()
    assert collector.refresh_if_due(source_id) is None
    assert requests == []
    with Session(database) as session:
        source = session.get(Source, source_id)
        source.enabled = True
        session.commit()
    scheduler.run_once()
    clock[0] += timedelta(minutes=2)
    with Session(database) as session:
        source = session.get(Source, source_id)
        source.refresh_interval_minutes = 1
        session.commit()
    scheduler.run_once()
    assert len(requests) == 2
    with Session(database) as session:
        session.delete(session.get(Source, source_id))
        session.commit()
    assert collector.refresh_if_due(source_id) is None


def test_failures_back_off_without_blocking_other_sources(setup, database):
    _, scheduler, source_id, clock, requests, replies = setup
    with Session(database) as session:
        first = session.get(Source, source_id)
        first.refresh_interval_minutes = 1
        first.consecutive_failures = 6
        session.add(Source(name="Second", feed_url="https://example.org/second"))
        session.commit()
    replies.extend([httpx.Response(503), httpx.Response(200, stream=httpx.ByteStream(RSS))])
    scheduler.run_once()
    with Session(database) as session:
        first = session.get(Source, source_id)
        assert first.last_error is not None
        assert first.consecutive_failures == 7
        assert [
            r.status for r in session.scalars(select(CollectionRun).order_by(CollectionRun.id))
        ] == ["error", "success"]
    clock[0] += timedelta(seconds=3599)
    scheduler.run_once()
    assert len(requests) == 2
    clock[0] += timedelta(seconds=1)
    scheduler.run_once()
    assert len(requests) == 4
    with Session(database) as session:
        assert session.get(Source, source_id).consecutive_failures == 0
        assert session.get(Source, source_id).last_error is None


def test_busy_collector_skips_pass_and_retries_without_creating_runs(setup, database):
    collector, scheduler, _, _, requests, _ = setup
    with collector.exclusive():
        scheduler.run_once()
    assert requests == []
    with Session(database) as session:
        assert session.scalars(select(CollectionRun)).all() == []
    scheduler.run_once()
    assert len(requests) == 1


def test_due_check_and_download_hold_shared_gate(setup, monkeypatch):
    collector, scheduler, source_id, _, requests, _ = setup
    original = collector.downloader.fetch

    def fetch(*args):
        with pytest.raises(RefreshRejected) as rejected:
            collector.refresh(source_id)
        assert rejected.value.status_code == 409
        with pytest.raises(RefreshRejected):
            with collector.exclusive():
                pytest.fail("Source writes must not enter during scheduled collection")
        return original(*args)

    monkeypatch.setattr(collector.downloader, "fetch", fetch)
    scheduler.run_once()
    assert len(requests) == 1


def test_unexpected_source_failure_does_not_stop_next_source(setup, database, monkeypatch, caplog):
    collector, scheduler, source_id, _, requests, _ = setup
    with Session(database) as session:
        session.add(Source(name="Second", feed_url="https://example.org/second"))
        session.commit()
    original = collector.refresh_if_due

    def refresh(source):
        if source == source_id:
            raise RuntimeError("private database URL")
        return original(source)

    monkeypatch.setattr(collector, "refresh_if_due", refresh)
    scheduler.run_once()
    assert len(requests) == 1
    assert "RuntimeError" in caplog.text
    assert "private database URL" not in caplog.text


def test_worker_repeats_after_scan_error_and_waits_between_passes(setup, monkeypatch, caplog):
    _, scheduler, _, _, _, _ = setup
    waits, passes = [], []

    def wait(seconds):
        waits.append(seconds)
        return len(waits) == 3

    def run_once():
        passes.append(True)
        if len(passes) == 1:
            raise RuntimeError("private database URL")

    monkeypatch.setattr(scheduler._stop, "wait", wait)
    monkeypatch.setattr(scheduler, "run_once", run_once)
    scheduler._run()
    assert waits == [30, 30, 30]
    assert len(passes) == 2
    assert "scan failed (RuntimeError)" in caplog.text
    assert "private database URL" not in caplog.text


@pytest.mark.anyio
async def test_lifespan_worker_keeps_api_responsive_and_finishes_before_disposal(
    database, monkeypatch
):
    entered, release, stopped = Event(), Event(), Event()
    calls = []

    def fetch(self, *args):
        calls.append(True)
        entered.set()
        assert release.wait(5), "Test did not release the download"
        return Download(url="https://example.org/feed", body=RSS)

    monkeypatch.setattr(FeedDownloader, "fetch", fetch)
    with Session(database) as session:
        session.add_all(
            [
                Source(name="First", feed_url="https://example.org/feed"),
                Source(name="Second", feed_url="https://example.org/second"),
            ]
        )
        session.commit()
    app = create_app(
        Settings(
            _env_file=None,
            database_url=database.url.render_as_string(hide_password=False),
            scheduler_enabled=True,
            scheduler_poll_seconds=1,
        )
    )
    lifespan = app.router.lifespan_context(app)
    await lifespan.__aenter__()
    scheduler = app.state.scheduler
    disposed = []
    event.listen(app.state.database_engine, "engine_disposed", lambda engine: disposed.append(True))
    original_stop = scheduler.stop

    def stop():
        scheduler._stop.set()
        stopped.set()
        original_stop()

    monkeypatch.setattr(scheduler, "stop", stop)
    shutdown = None
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (await client.get("/api/health")).status_code == 200
            assert (await client.get("/api/sources")).status_code == 200
            assert (await client.post("/api/sources/1/refresh")).status_code == 409
        shutdown = asyncio.create_task(lifespan.__aexit__(None, None, None))
        assert await asyncio.to_thread(stopped.wait, 3)
        assert not disposed
        assert not shutdown.done()
    finally:
        release.set()
        if shutdown is not None:
            await asyncio.wait_for(shutdown, 5)
        else:
            await lifespan.__aexit__(None, None, None)
    assert not scheduler._thread.is_alive()
    assert disposed == [True]
    assert calls == [True]
    with Session(database) as session:
        assert session.scalar(select(CollectionRun)).status == "success"


@pytest.mark.anyio
async def test_disabled_scheduler_does_not_start_worker(database, monkeypatch):
    def fail(self):
        pytest.fail("Disabled scheduler started a worker")

    monkeypatch.setattr(CollectionScheduler, "start", fail)
    monkeypatch.setenv("TNR_SCHEDULER_ENABLED", "false")
    app = create_app(
        Settings(_env_file=None, database_url=database.url.render_as_string(hide_password=False))
    )
    async with app.router.lifespan_context(app):
        assert app.state.scheduler is None


def test_idle_worker_stops_without_waiting_for_full_poll_interval(setup):
    _, scheduler, _, _, requests, _ = setup
    scheduler.poll_seconds = 300
    scheduler.start()
    scheduler.stop()
    assert not scheduler._thread.is_alive()
    assert requests == []


@pytest.mark.parametrize("value", [0, -1, 301, 1.5])
def test_invalid_poll_interval_is_rejected(value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, scheduler_poll_seconds=value)
