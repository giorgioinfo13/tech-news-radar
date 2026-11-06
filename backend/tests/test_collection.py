from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

import httpx
import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.collection.download import Download, FeedDownloader
from app.config import Settings
from app.main import create_app
from app.models import LOCAL_OWNER_ID, Article, ArticleReadState, CollectionRun, Source

pytestmark = pytest.mark.anyio
FIXTURES = Path(__file__).parent / "fixtures"
RSS = (FIXTURES / "rss.xml").read_bytes()
ATOM = (FIXTURES / "atom.xml").read_bytes()


@pytest.fixture
async def setup(database, monkeypatch):
    settings = Settings(
        _env_file=None,
        database_url=database.url.render_as_string(hide_password=False),
        local_user_id=LOCAL_OWNER_ID,
        scheduler_enabled=False,
    )
    app = create_app(settings)
    replies, requests = [], []
    clock = [datetime(2026, 11, 5, tzinfo=UTC)]
    monkeypatch.setattr("app.collection.service.utc_now", lambda: clock[0])

    def handle(request):
        requests.append(request)
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    async with app.router.lifespan_context(app):
        collector = app.state.collector
        collector.downloader = FeedDownloader(
            settings,
            resolver=lambda host, port: "93.184.215.14",
            transport=httpx.MockTransport(handle),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/sources",
                json={
                    "name": "Test",
                    "feed_url": "https://example.org/feed",
                    "category_id": 1,
                },
            )
            assert response.status_code == 201
            source_id = response.json()["id"]
            await client.put(f"/api/subscriptions/{source_id}")
            yield client, collector, source_id, replies, requests, clock


def reply(body=RSS, **headers):
    return httpx.Response(200, headers=headers, stream=httpx.ByteStream(body))


async def test_refresh_persists_articles_then_uses_conditional_304(setup, database):
    client, _, source_id, replies, requests, clock = setup
    path = f"/api/sources/{source_id}/refresh"
    replies.append(reply(etag='"v1"', **{"last-modified": "Thu, 01 Jan 2026 08:00:00 GMT"}))
    response = await client.post(path)
    assert response.status_code == 200, response.text
    run = response.json()
    assert (run["status"], run["articles_seen"], run["articles_added"]) == ("success", 3, 2)
    assert run["finished_at"] is not None
    articles = (await client.get("/api/articles")).json()["items"]
    assert len(articles) == 2
    assert all(article["source"]["category"]["id"] == 1 for article in articles)
    await client.patch(f"/api/articles/{articles[0]['id']}", json={"is_read": True})
    immediate = await client.post(path)
    assert immediate.status_code == 429
    assert immediate.headers["retry-after"] == "30"
    assert len(requests) == 1
    clock[0] += timedelta(seconds=31)
    replies.append(httpx.Response(304))
    cached = await client.post(path)
    assert cached.status_code == 200
    assert cached.json()["status"] == "not_modified"
    assert cached.json()["articles_added"] == 0
    assert requests[-1].headers["if-none-match"] == '"v1"'
    assert requests[-1].headers["if-modified-since"] == "Thu, 01 Jan 2026 08:00:00 GMT"
    with Session(database) as session:
        source = session.get(Source, source_id)
        assert source.last_checked_at == source.last_success_at == clock[0]
        assert source.last_error is None
        assert source.etag == '"v1"'
        assert session.get(ArticleReadState, (LOCAL_OWNER_ID, articles[0]["id"])) is not None
    history = (await client.get(f"/api/sources/{source_id}/runs")).json()
    assert history["total"] == 2
    assert [item["status"] for item in history["items"]] == ["not_modified", "success"]


async def test_repeat_and_changed_guid_or_url_deduplicate_without_overwriting(setup, database):
    client, _, source_id, replies, _, clock = setup
    path = f"/api/sources/{source_id}/refresh"
    replies.append(reply())
    await client.post(path)
    original = (await client.get("/api/articles")).json()["items"]
    await client.patch(f"/api/articles/{original[0]['id']}", json={"is_read": True})
    variations = [
        RSS,
        RSS.replace(b"first?original=1#section", b"changed-url"),
        RSS.replace(b">first</guid>", b">changed-guid</guid>"),
        RSS.replace(b"#section", b"#other"),
    ]
    for body in variations:
        clock[0] += timedelta(seconds=31)
        replies.append(reply(body))
        result = await client.post(path)
        assert result.status_code == 200
        assert result.json()["articles_added"] == 0
    with Session(database) as session:
        articles = session.scalars(select(Article).where(Article.source_id == source_id)).all()
        assert len(articles) == 2
        assert any(
            article.url == "https://example.org/first?original=1#section" for article in articles
        )
        assert session.get(ArticleReadState, (LOCAL_OWNER_ID, original[0]["id"])) is not None


async def test_duplicates_inside_feed_and_across_sources(setup):
    client, _, source_id, replies, _, _ = setup
    duplicate = RSS.replace(
        b"</channel>",
        RSS.split(b"<item>")[1].split(b"</item>")[0].join([b"<item>", b"</item></channel>"]),
    )
    replies.append(reply(duplicate))
    response = await client.post(f"/api/sources/{source_id}/refresh")
    assert response.json()["articles_seen"] == 4
    assert response.json()["articles_added"] == 2
    second = (
        await client.post(
            "/api/sources",
            json={
                "name": "Second",
                "feed_url": "https://example.org/second-feed",
            },
        )
    ).json()["id"]
    replies.append(reply())
    assert (await client.post(f"/api/sources/{second}/refresh")).json()["articles_added"] == 2
    assert (await client.get("/api/articles?subscribed_only=false")).json()["total"] == 4


async def test_atom_refresh_and_missing_publication_dates(setup):
    client, _, source_id, replies, _, _ = setup
    replies.append(reply(ATOM))
    response = await client.post(f"/api/sources/{source_id}/refresh")
    assert response.status_code == 200
    assert response.json()["articles_added"] == 2
    items = (await client.get("/api/articles")).json()["items"]
    assert any(item["published_at"] is None for item in items)
    assert any(item["published_at"] == "2026-01-02T14:30:00Z" for item in items)


@pytest.mark.parametrize("failure", ["timeout", "status", "invalid", "oversized"])
async def test_failures_record_diagnostics_keep_cache_and_backoff_then_recover(
    setup, database, failure
):
    client, _, source_id, replies, requests, clock = setup
    path = f"/api/sources/{source_id}/refresh"
    replies.append(reply(etag='"good"'))
    await client.post(path)
    success_time = clock[0]
    clock[0] += timedelta(seconds=31)
    replies.append(
        {
            "timeout": httpx.ReadTimeout("https://secret.invalid/?token=private"),
            "status": httpx.Response(503),
            "invalid": reply(b"<html>not news</html>", etag='"bad"'),
            "oversized": httpx.Response(200, headers={"content-length": "3000000"}),
        }[failure]
    )
    result = await client.post(path)
    assert result.status_code == 502
    assert result.json()["status"] == "error"
    assert result.json()["error_message"]
    assert "private" not in result.text
    assert result.json()["articles_added"] == 0
    with Session(database) as session:
        source = session.get(Source, source_id)
        assert source.last_success_at == success_time
        assert source.last_checked_at == clock[0]
        assert source.last_error == result.json()["error_message"]
        assert source.consecutive_failures == 1
        assert source.etag == '"good"'
    assert (await client.get("/api/articles")).json()["total"] == 2
    blocked = await client.post(path)
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "60"
    clock[0] += timedelta(seconds=61)
    replies.append(reply(etag='"recovered"'))
    assert (await client.post(path)).json()["status"] == "success"
    assert requests[-1].headers["if-none-match"] == '"good"'
    source = (await client.get("/api/sources")).json()["items"][0]
    assert source["last_error"] is None
    assert source["consecutive_failures"] == 0


async def test_disabled_missing_and_overlapping_refresh_do_not_start_runs(setup):
    client, collector, source_id, _, requests, _ = setup
    path = f"/api/sources/{source_id}"
    assert (await client.post("/api/sources/99999/refresh")).status_code == 404
    await client.patch(path, json={"enabled": False})
    assert (await client.post(f"{path}/refresh")).status_code == 409
    await client.patch(path, json={"enabled": True})
    with collector.exclusive():
        assert (await client.post(f"{path}/refresh")).status_code == 409
        assert (await client.patch(path, json={"name": "Blocked"})).status_code == 409
        assert (await client.delete(path)).status_code == 409
    assert (await client.get(f"{path}/runs")).json()["total"] == 0
    assert not requests


async def test_active_download_has_no_open_db_transaction_and_blocks_source_changes(
    setup, database
):
    client, collector, source_id, _, _, _ = setup
    started, finish = Event(), Event()

    def fetch(*args):
        started.set()
        assert finish.wait(5)
        return Download(RSS, "https://example.org/feed")

    collector.downloader.fetch = fetch
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(collector.refresh, source_id)
        try:
            assert started.wait(5)
            with Session(database) as session:
                running = session.scalar(
                    select(CollectionRun).where(CollectionRun.source_id == source_id)
                )
                assert running.status == "running"
                session.add(Source(name="Concurrent write", feed_url="https://other.example/feed"))
                session.commit()
            path = f"/api/sources/{source_id}"
            assert (
                await client.patch(path, json={"feed_url": "https://other.example/feed"})
            ).status_code == 409
            assert (await client.delete(path)).status_code == 409
            assert (await client.post(f"{path}/refresh")).status_code == 409
        finally:
            finish.set()
        assert future.result(timeout=5).status == "success"


async def test_interrupted_runs_recovered_on_next_refresh(setup, database):
    client, _, source_id, replies, _, clock = setup
    with Session(database) as session:
        session.add(CollectionRun(source_id=source_id, started_at=clock[0] - timedelta(minutes=5)))
        session.commit()
    replies.append(reply())
    assert (await client.post(f"/api/sources/{source_id}/refresh")).status_code == 200
    history = (await client.get(f"/api/sources/{source_id}/runs")).json()["items"]
    assert [item["status"] for item in history] == ["success", "error"]
    assert history[1]["finished_at"] is not None
    assert "interrupted" in history[1]["error_message"]


async def test_partial_insert_failure_rolls_back_and_releases_lock(setup, database):
    client, _, source_id, replies, _, clock = setup
    replies.append(reply())

    inserted = []

    def fail_insert(mapper, connection, article):
        inserted.append(article.url)
        if len(inserted) == 2:
            raise RuntimeError("do not expose secret SQL details")

    event.listen(Article, "after_insert", fail_insert)
    try:
        result = await client.post(f"/api/sources/{source_id}/refresh")
    finally:
        event.remove(Article, "after_insert", fail_insert)
    assert len(inserted) == 2
    assert result.status_code == 502
    assert result.json()["error_message"] == "Unexpected collection failure"
    assert (await client.get("/api/articles")).json()["total"] == 0
    assert result.json()["articles_added"] == 0
    clock[0] += timedelta(seconds=61)
    replies.append(reply())
    assert (await client.post(f"/api/sources/{source_id}/refresh")).json()["articles_added"] == 2
