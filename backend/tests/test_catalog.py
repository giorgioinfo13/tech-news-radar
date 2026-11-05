import argparse

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import CatalogEntry, all_items, import_catalog, load_catalog, local_api_url
from app.models import Category, Source


def entry():
    return CatalogEntry(
        name="Example", feed_url="https://example.org/rss", category_slug="software-engineering"
    )


def test_bundled_catalog_has_unique_valid_urls_and_known_categories(database):
    catalog = load_catalog()
    assert len(catalog) == 11
    with Session(database) as session:
        slugs = set(session.scalars(select(Category.slug)))
    assert all(item.category_slug in slugs for item in catalog)


@pytest.mark.anyio
async def test_repeat_import_preserves_source_and_category_edits(client, database):
    first = await import_catalog(client, [entry()])
    assert first.added == 1
    with Session(database) as session:
        source = session.scalar(select(Source))
        category = session.get(Category, source.category_id)
        category.name = "My category"
        source.name = "My source"
        source.enabled = False
        source.refresh_interval_minutes = 120
        source.category_id = None
        session.commit()
    repeated = await import_catalog(client, [entry()], refresh=True)
    assert repeated.added == 0
    assert repeated.existing == repeated.disabled == 1
    assert repeated.refreshed == 0
    sources = (await client.get("/api/sources")).json()
    assert sources["total"] == 1
    assert sources["items"][0]["name"] == "My source"
    assert sources["items"][0]["category_id"] is None
    assert sources["items"][0]["refresh_interval_minutes"] == 120
    categories = (await client.get("/api/categories")).json()["items"]
    assert any(item["name"] == "My category" for item in categories)


@pytest.mark.anyio
async def test_missing_category_is_not_recreated(client, database):
    with Session(database) as session:
        category = session.scalar(select(Category).where(Category.slug == entry().category_slug))
        session.delete(category)
        session.commit()
    result = await import_catalog(client, [entry()])
    assert result.added == 1
    assert (await client.get("/api/categories")).json()["total"] == 7
    assert (await client.get("/api/sources")).json()["items"][0]["category_id"] is None


@pytest.mark.anyio
@pytest.mark.parametrize("failure", [502, 429, 409, "timeout"])
async def test_refresh_continues_after_failure_and_ignores_non_catalog_sources(failure):
    entries = [
        entry(),
        entry().model_copy(update={"name": "Second", "feed_url": "https://other.org/rss"}),
    ]
    refreshed = []

    def handler(request):
        if request.url.path == "/api/categories":
            return httpx.Response(200, json={"items": [], "total": 0})
        if request.url.path == "/api/sources":
            sources = [
                {"id": i, "feed_url": item.feed_url, "enabled": True}
                for i, item in enumerate(entries, 1)
            ]
            sources.append({"id": 3, "feed_url": "https://personal.org/rss", "enabled": True})
            return httpx.Response(200, json={"items": sources, "total": 3})
        refreshed.append(request.url.path)
        if len(refreshed) == 1:
            if failure == "timeout":
                raise httpx.ReadTimeout("Timeout")
            return httpx.Response(failure)
        return httpx.Response(200, json={"articles_added": 7})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as client:
        result = await import_catalog(client, entries, refresh=True)
    assert result.failed == result.refreshed == 1
    assert refreshed == ["/api/sources/1/refresh", "/api/sources/2/refresh"]


@pytest.mark.anyio
async def test_catalog_reads_all_source_pages():
    def handler(request):
        offset = int(request.url.params["offset"])
        items = [{"id": i} for i in range(offset, min(offset + 100, 101))]
        return httpx.Response(200, json={"items": items, "total": 101})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as client:
        assert len(await all_items(client, "/api/sources")) == 101


@pytest.mark.parametrize(
    "url",
    [
        "https://example.org",
        "http://user:pass@localhost",
        "http://localhost/api",
        "http://localhost/?key=x",
    ],
)
def test_cli_rejects_remote_or_ambiguous_api_origins(url):
    with pytest.raises(argparse.ArgumentTypeError):
        local_api_url(url)


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:8000", "http://localhost:18000", "http://[::1]:8000"]
)
def test_cli_accepts_local_api_origins(url):
    assert local_api_url(url).startswith(url)
