from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.models import (
    LOCAL_OWNER_ID,
    Article,
    ArticleReadState,
    CollectionRun,
    Source,
    Subscription,
)

pytestmark = pytest.mark.anyio


async def add_source(client: AsyncClient, **changes) -> dict:
    response = await client.post(
        "/api/sources",
        json={"name": "Example", "feed_url": "https://example.org/feed.xml", **changes},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_category_crud_pagination_and_conflict_rollback(client: AsyncClient):
    initial = (await client.get("/api/categories")).json()
    assert initial["total"] == 8
    response = await client.post(
        "/api/categories", json={"name": " Custom ", "slug": " custom ", "sort_order": -1}
    )
    assert response.status_code == 201
    category = response.json()
    assert category["name"] == "Custom"
    assert category["slug"] == "custom"
    path = f"/api/categories/{category['id']}"
    page = (await client.get("/api/categories?limit=1&offset=0")).json()
    assert page == {"items": [category], "total": 9, "limit": 1, "offset": 0}
    second = (await client.get("/api/categories?limit=1&offset=1")).json()
    assert second["items"][0]["id"] != category["id"]
    assert second["total"] == 9

    for data in [
        {"name": "Custom", "slug": "other"},
        {"name": "Other", "slug": "custom"},
    ]:
        assert (await client.post("/api/categories", json=data)).status_code == 409
    duplicate = initial["items"][0]["slug"]
    assert (
        await client.patch(path, json={"name": "Not persisted", "slug": duplicate})
    ).status_code == 409
    assert (await client.patch(path, json={})).json() == category
    changed = await client.patch(path, json={"name": "Renamed", "sort_order": 99})
    assert changed.status_code == 200
    assert changed.json()["name"] == "Renamed"
    assert changed.json()["slug"] == "custom"
    deleted = await client.delete(path)
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert (await client.delete(path)).status_code == 404
    assert (await client.patch(path, json={"name": "Gone"})).status_code == 404


@pytest.mark.parametrize(
    "data",
    [
        {"name": " "},
        {"slug": "Upper case"},
        {"slug": "bad_slug"},
        {"name": "a" * 121},
        {"sort_order": 1.5},
        {"sort_order": True},
        {"id": 1},
    ],
)
async def test_invalid_category_inputs(client: AsyncClient, data: dict):
    assert (
        await client.post("/api/categories", json={"name": "Test", "slug": "test", **data})
    ).status_code == 422
    assert (await client.patch("/api/categories/1", json=data)).status_code == 422


@pytest.mark.parametrize("field", ["name", "slug", "sort_order"])
async def test_category_patch_rejects_explicit_null(client: AsyncClient, field: str):
    assert (await client.patch("/api/categories/1", json={field: None})).status_code == 422


async def test_source_crud_filters_and_readonly_fields(client: AsyncClient):
    category = (await client.get("/api/categories")).json()["items"][0]
    source = await add_source(client, name=" Example ", category_id=category["id"])
    path = f"/api/sources/{source['id']}"
    assert source["name"] == "Example"
    assert source["category"] == category
    assert source["enabled"] is True
    assert source["refresh_interval_minutes"] == 60
    assert source["last_checked_at"] is None
    assert source["last_error"] is None
    assert source["created_at"].endswith("Z")
    assert "etag" not in source
    assert (await client.patch(path, json={})).json() == source
    changed = await client.patch(path, json={"enabled": False, "refresh_interval_minutes": 120})
    assert changed.status_code == 200
    assert changed.json()["enabled"] is False
    assert changed.json()["refresh_interval_minutes"] == 120
    assert changed.json()["feed_url"] == source["feed_url"]
    await add_source(client, name="Another", feed_url="https://example.org/other")
    assert (await client.get("/api/sources?enabled=true")).json()["total"] == 1
    filtered = (await client.get(f"/api/sources?category_id={category['id']}&enabled=false")).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["id"] == source["id"]
    page = (await client.get("/api/sources?limit=1&offset=1")).json()
    assert page["total"] == 2
    assert page["items"][0]["id"] == source["id"]
    assert (await client.patch(path, json={"category_id": None})).json()["category"] is None
    for field in ["id", "last_error", "last_checked_at", "etag", "consecutive_failures"]:
        assert (await client.patch(path, json={field: "forbidden"})).status_code == 422
    assert (await client.delete(path)).status_code == 204
    assert (await client.delete(path)).status_code == 404
    assert (await client.patch(path, json={"enabled": True})).status_code == 404


@pytest.mark.parametrize(
    "data",
    [
        {"name": "  "},
        {"name": "a" * 201},
        {"feed_url": "not a URL"},
        {"feed_url": "file:///etc/passwd"},
        {"feed_url": "ftp://example.org/feed"},
        {"feed_url": "https://user:secret@example.org/feed"},
        {"feed_url": "https://example.org/feed#section"},
        {"feed_url": "https://example.org/" + "a" * 2048},
        {"enabled": "false"},
        {"refresh_interval_minutes": 0},
        {"refresh_interval_minutes": 10081},
        {"refresh_interval_minutes": 1.5},
        {"category_id": 0},
        {"category_id": 2**63},
        {"category_id": True},
        {"created_at": "2026-01-01T00:00:00Z"},
    ],
)
async def test_invalid_source_inputs(client: AsyncClient, data: dict):
    source = await add_source(client)
    assert (
        await client.post(
            "/api/sources", json={"name": "Test", "feed_url": "https://example.org/new", **data}
        )
    ).status_code == 422
    assert (await client.patch(f"/api/sources/{source['id']}", json=data)).status_code == 422


@pytest.mark.parametrize("field", ["name", "feed_url", "enabled", "refresh_interval_minutes"])
async def test_source_patch_rejects_null_required_fields(client: AsyncClient, field: str):
    source = await add_source(client)
    assert (
        await client.patch(f"/api/sources/{source['id']}", json={field: None})
    ).status_code == 422


async def test_source_url_normalization_duplicates_and_missing_category(client: AsyncClient):
    source = await add_source(client, feed_url=" HTTPS://EXAMPLE.ORG:443 ")
    assert source["feed_url"] == "https://example.org/"
    assert (
        await client.post(
            "/api/sources", json={"name": "Duplicate", "feed_url": "https://example.org/"}
        )
    ).status_code == 409
    other = await add_source(client)
    path = f"/api/sources/{other['id']}"
    assert (await client.patch(path, json={"feed_url": source["feed_url"]})).status_code == 409
    assert (await client.patch(path, json={})).json() == other
    assert (await client.patch(path, json={"category_id": 999999})).status_code == 404
    assert (
        await client.post(
            "/api/sources",
            json={
                "name": "Missing",
                "feed_url": "https://example.org/missing",
                "category_id": 999999,
            },
        )
    ).status_code == 404


@pytest.fixture
def news(database: Engine) -> dict:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    with Session(database) as session:
        first = Source(name="First", feed_url="https://example.org/first", category_id=1)
        second = Source(name="Second", feed_url="https://example.org/second", category_id=2)
        session.add_all([first, second])
        session.flush()
        articles = [
            Article(
                source_id=first.id,
                url="https://example.org/a?original=1",
                title="Older AI news",
                description="Progress at 100%",
                published_at=timestamp,
                fetched_at=timestamp,
            ),
            Article(
                source_id=second.id,
                url="https://example.org/b",
                title="Newer story",
                description="An AI agent",
                published_at=timestamp + timedelta(days=1),
                fetched_at=timestamp,
            ),
            Article(
                source_id=first.id,
                url="https://example.org/c",
                title="Unknown date_1",
                published_at=None,
                fetched_at=timestamp + timedelta(days=2),
            ),
            Article(
                source_id=first.id,
                url="https://example.org/d",
                title="Tied date",
                published_at=timestamp + timedelta(days=2),
                fetched_at=timestamp,
            ),
        ]
        session.add_all(articles)
        session.flush()
        session.add(ArticleReadState(user_id=LOCAL_OWNER_ID, article_id=articles[1].id))
        session.add_all(
            [
                Subscription(user_id=LOCAL_OWNER_ID, source_id=source.id)
                for source in (first, second)
            ]
        )
        session.add_all(
            [
                CollectionRun(
                    source_id=first.id,
                    started_at=timestamp,
                    finished_at=timestamp,
                    status="error",
                    error_message="Timed out",
                ),
                CollectionRun(
                    source_id=first.id,
                    started_at=timestamp,
                    finished_at=timestamp,
                    status="success",
                    articles_seen=4,
                    articles_added=4,
                ),
                CollectionRun(source_id=second.id, started_at=timestamp),
            ]
        )
        session.commit()
        return {"first": first.id, "second": second.id, "articles": [a.id for a in articles]}


async def test_article_order_pagination_original_fields_and_empty_page(
    client: AsyncClient, news: dict
):
    result = (await client.get("/api/articles")).json()
    assert result["total"] == 4
    assert [item["id"] for item in result["items"]] == list(reversed(news["articles"]))
    assert result["items"][1]["published_at"] is None
    assert result["items"][1]["fetched_at"] == "2026-01-03T00:00:00Z"
    assert result["items"][-1]["url"] == "https://example.org/a?original=1"
    assert result["items"][-1]["source"]["name"] == "First"
    assert result["items"][-1]["source"]["category"]["id"] == 1
    page = (await client.get("/api/articles?limit=2&offset=1")).json()
    assert page == {"items": result["items"][1:3], "total": 4, "limit": 2, "offset": 1}
    assert (await client.get("/api/articles?offset=100")).json() == {
        "items": [],
        "total": 4,
        "limit": 50,
        "offset": 100,
    }


@pytest.mark.parametrize(
    ("query", "indexes"),
    [
        ("category_id=1", [3, 2, 0]),
        ("category_id=2&is_read=true", [1]),
        ("is_read=false", [3, 2, 0]),
        ("q=ai", [1, 0]),
        ("q=100%25", [0]),
        ("q=_", [2]),
        ("q=%25", [0]),
        ("q=%27%20OR%201%3D1--", []),
        ("q=%20%20", [3, 2, 1, 0]),
        ("category_id=999999", []),
    ],
)
async def test_article_filters_and_literal_search(client: AsyncClient, news: dict, query, indexes):
    result = (await client.get(f"/api/articles?{query}")).json()
    assert result["total"] == len(indexes)
    assert [item["id"] for item in result["items"]] == [news["articles"][i] for i in indexes]
    source_filter = (await client.get(f"/api/articles?source_id={news['first']}&q=ai")).json()
    assert [item["id"] for item in source_filter["items"]] == [news["articles"][0]]


async def test_read_status_is_idempotent_and_persisted(
    client: AsyncClient, database: Engine, news: dict
):
    article_id = news["articles"][0]
    path = f"/api/articles/{article_id}"
    for _ in range(2):
        response = await client.patch(path, json={"is_read": True})
        assert response.status_code == 200
        assert response.json()["is_read"] is True
    with Session(database) as session:
        assert session.get(ArticleReadState, (LOCAL_OWNER_ID, article_id)) is not None
    assert (await client.get("/api/articles?is_read=true")).json()["total"] == 2
    assert (await client.patch(path, json={"is_read": False})).json()["is_read"] is False
    for body in [{}, {"is_read": None}, {"is_read": "false"}, {"is_read": True, "title": "Edited"}]:
        assert (await client.patch(path, json=body)).status_code == 422
    assert (await client.patch("/api/articles/999999", json={"is_read": True})).status_code == 404


async def test_category_changes_and_cascade_deletion(client: AsyncClient, news: dict):
    source_path = f"/api/sources/{news['first']}"
    assert (await client.patch(source_path, json={"category_id": 2})).status_code == 200
    assert (await client.get("/api/articles?category_id=2")).json()["total"] == 4
    assert (await client.delete("/api/categories/2")).status_code == 204
    articles = (await client.get("/api/articles")).json()["items"]
    assert len(articles) == 4
    assert all(article["source"]["category"] is None for article in articles)
    assert (await client.delete(source_path)).status_code == 204
    remaining = (await client.get("/api/articles")).json()
    assert remaining["total"] == 1
    assert remaining["items"][0]["source_id"] == news["second"]
    assert (await client.get(f"{source_path}/runs")).status_code == 404
    assert (await client.get(f"/api/sources/{news['second']}/runs")).json()["total"] == 1


async def test_runs_are_paginated_and_scoped(client: AsyncClient, news: dict):
    path = f"/api/sources/{news['first']}/runs"
    result = (await client.get(path, params={"limit": 1})).json()
    assert result["total"] == 2
    assert result["items"][0]["status"] == "success"
    second = (await client.get(path, params={"limit": 1, "offset": 1})).json()
    assert second["items"][0]["error_message"] == "Timed out"
    assert second["items"][0]["source_id"] == news["first"]


async def test_feed_url_change_resets_diagnostics_but_preserves_content(
    client: AsyncClient,
    database: Engine,
    news: dict,
):
    with Session(database) as session:
        source = session.get(Source, news["first"])
        source.etag = '"old"'
        source.last_modified = "Thu, 01 Jan 2026 00:00:00 GMT"
        source.last_checked_at = source.last_success_at = datetime(2026, 1, 1, tzinfo=UTC)
        source.last_error = "Timeout"
        source.consecutive_failures = 2
        session.commit()
    path = f"/api/sources/{news['first']}"
    unchanged = await client.patch(
        path, json={"name": "Renamed", "feed_url": "https://example.org/first"}
    )
    assert unchanged.json()["consecutive_failures"] == 2
    result = await client.patch(path, json={"feed_url": "https://example.org/replacement"})
    assert result.status_code == 200
    for field in ["last_checked_at", "last_success_at", "last_error"]:
        assert result.json()[field] is None
    assert result.json()["consecutive_failures"] == 0
    with Session(database) as session:
        source = session.get(Source, news["first"])
        assert source.etag is None
        assert source.last_modified is None
        assert (
            len(session.scalars(select(Article).where(Article.source_id == source.id)).all()) == 3
        )
    assert (await client.get(f"{path}/runs")).json()["total"] == 2


@pytest.mark.parametrize("endpoint", ["categories", "sources", "articles", "sources/999999/runs"])
@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", f"offset={2**63}"])
async def test_pagination_rejects_invalid_values(client: AsyncClient, endpoint: str, query: str):
    assert (await client.get(f"/api/{endpoint}?{query}")).status_code == 422


@pytest.mark.parametrize(
    "query", ["source_id=0", f"category_id={2**63}", "is_read=maybe", "q=" + "a" * 201]
)
async def test_invalid_article_filters(client: AsyncClient, query: str):
    assert (await client.get(f"/api/articles?{query}")).status_code == 422


async def test_empty_collections_and_no_collection_side_effects(client: AsyncClient):
    assert (await client.get("/api/articles")).json()["items"] == []
    assert (await client.get("/api/sources")).json()["total"] == 0
    source = await add_source(client)
    assert (await client.get(f"/api/sources/{source['id']}/runs")).json()["total"] == 0
    assert (await client.get("/api/articles")).json()["total"] == 0


@pytest.mark.parametrize("resource_id", [0, -1, 2**63])
async def test_resource_ids_have_database_safe_bounds(client: AsyncClient, resource_id: int):
    assert (await client.delete(f"/api/categories/{resource_id}")).status_code == 422
    assert (await client.delete(f"/api/sources/{resource_id}")).status_code == 422
    assert (
        await client.patch(f"/api/articles/{resource_id}", json={"is_read": True})
    ).status_code == 422
