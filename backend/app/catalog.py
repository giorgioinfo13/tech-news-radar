"""Import the optional starter catalog through the running local API."""

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

import httpx
from pydantic import TypeAdapter

from app.schemas import FeedUrl, InputModel, Slug, SourceName

CATALOG_PATH = Path(__file__).with_name("source_catalog.json")


class CatalogEntry(InputModel):
    name: SourceName
    feed_url: FeedUrl
    category_slug: Slug


@dataclass
class ImportResult:
    added: int = 0
    existing: int = 0
    refreshed: int = 0
    failed: int = 0
    disabled: int = 0


def load_catalog() -> list[CatalogEntry]:
    entries = TypeAdapter(list[CatalogEntry]).validate_python(
        json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    )
    if len({entry.feed_url for entry in entries}) != len(entries):
        raise ValueError("Catalog contains duplicate feed URLs")
    return entries


async def all_items(client: httpx.AsyncClient, path: str) -> list[dict]:
    items = []
    while True:
        response = await client.get(path, params={"limit": 100, "offset": len(items)})
        response.raise_for_status()
        page = response.json()
        items.extend(page["items"])
        if not page["items"] or len(items) >= page["total"]:
            return items


async def import_catalog(
    client: httpx.AsyncClient, entries: list[CatalogEntry], *, refresh: bool = False
) -> ImportResult:
    categories = {item["slug"]: item["id"] for item in await all_items(client, "/api/categories")}
    sources = {item["feed_url"]: item for item in await all_items(client, "/api/sources")}
    result = ImportResult()
    for entry in entries:
        source = sources.get(entry.feed_url)
        if source is None:
            category_id = categories.get(entry.category_slug)
            if category_id is None:
                print(f"{entry.name}: category absent; importing without a category.", flush=True)
            response = await client.post(
                "/api/sources",
                json={"name": entry.name, "feed_url": entry.feed_url, "category_id": category_id},
            )
            response.raise_for_status()
            source = response.json()
            sources[entry.feed_url] = source
            result.added += 1
            print(f"{entry.name}: added.", flush=True)
        else:
            result.existing += 1
            print(f"{entry.name}: already present; configuration preserved.", flush=True)
        if not refresh:
            continue
        if not source["enabled"]:
            result.disabled += 1
            print(f"{entry.name}: disabled; refresh skipped.", flush=True)
            continue
        try:
            response = await client.post(f"/api/sources/{source['id']}/refresh")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            result.failed += 1
            status = (
                f"HTTP {exc.response.status_code}"
                if isinstance(exc, httpx.HTTPStatusError)
                else "connection error"
            )
            print(
                f"{entry.name}: refresh failed ({status}); inspect Sources in the UI.", flush=True
            )
        else:
            result.refreshed += 1
            print(f"{entry.name}: {response.json()['articles_added']} new articles.", flush=True)
    return result


def local_api_url(value: str) -> str:
    try:
        url = httpx.URL(value)
        if (
            url.scheme != "http"
            or url.host not in {"127.0.0.1", "::1", "localhost"}
            or url.userinfo
            or url.query
            or url.fragment
            or url.path != "/"
        ):
            raise ValueError
    except (ValueError, httpx.InvalidURL) as exc:
        raise argparse.ArgumentTypeError(
            "Use a local HTTP API origin, such as http://127.0.0.1:8000"
        ) from exc
    return str(url)


async def run(api_url: str, refresh: bool) -> int:
    # Go through the same API/collector lock as the UI, never a second collector process.
    async with httpx.AsyncClient(base_url=api_url, timeout=240, trust_env=False) as client:
        try:
            result = await import_catalog(client, load_catalog(), refresh=refresh)
        except httpx.HTTPError:
            print("Import interrupted. Check the local API and migrations, then rerun the command.")
            return 1
    print(
        f"Added: {result.added}; existing: {result.existing}; refreshed: {result.refreshed}; "
        f"disabled: {result.disabled}; failed: {result.failed}."
    )
    return int(result.failed > 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", type=local_api_url, default="http://127.0.0.1:8000")
    parser.add_argument(
        "--refresh", action="store_true", help="Refresh enabled catalog sources sequentially"
    )
    args = parser.parse_args()
    return asyncio.run(run(args.api_url, args.refresh))


if __name__ == "__main__":
    raise SystemExit(main())
