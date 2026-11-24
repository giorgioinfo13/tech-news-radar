"""Publisher-declared image URLs for the supported catalog feeds."""

import json
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

GALEAZZI = "https://andreagaleazzi.com/feed/"
DDAY = "https://www.dday.it/rss"
HDBLOG = "https://www.hdblog.it/feed/"
IMPORT_AI = "https://importai.substack.com/feed"

# Match the configured feed, including the channel on shared platforms.
IMAGE_HOSTS: dict[str, list[str]] = json.loads(
    Path(__file__).with_name("thumbnail_sources.json").read_text(encoding="utf-8")
)


def records(item: dict, field: str) -> Iterator[dict]:
    values = item.get(field)
    if isinstance(values, list):
        yield from (value for value in values if isinstance(value, dict))


def image_candidates(item: dict, feed_url: str, publisher_image: str) -> Iterator[str]:
    if feed_url == HDBLOG:
        yield item.get("thumb", "")
        yield item.get("thumb_intermedia", "")
    elif feed_url == GALEAZZI:
        yield publisher_image
    for media in records(item, "media_thumbnail"):
        yield media.get("url", "")
    for media in records(item, "media_content"):
        if media.get("medium") == "image" or str(media.get("type", "")).lower().startswith(
            "image/"
        ):
            yield media.get("url", "")
    for link in records(item, "links"):
        if link.get("rel") == "enclosure" and str(link.get("type", "")).lower().startswith(
            "image/"
        ):
            yield link.get("href", "")


def thumbnail_url(
    item: dict, feed_url: str, article_url: str, publisher_image: str, channel_image: str
) -> str | None:
    hosts = IMAGE_HOSTS.get(feed_url)
    if not hosts:
        return None
    for value in image_candidates(item, feed_url, publisher_image):
        if not isinstance(value, str) or not value or len(value) > 2048:
            continue
        if not value.strip() or "\\" in value or any(ord(char) < 32 for char in value):
            continue
        try:
            absolute = urljoin(article_url, value.strip())
            url = urlsplit(absolute)
            if (
                url.scheme != "https"
                or url.hostname not in hosts
                or url.username is not None
                or url.port not in (443, None)
                or len(absolute) > 2048
            ):
                continue
            # Substack resizes its channel logo using different URL prefixes.
            if (
                feed_url == IMPORT_AI
                and channel_image
                and (
                    unquote(url.path).rsplit("/", 1)[-1]
                    == unquote(urlsplit(channel_image).path).rsplit("/", 1)[-1]
                )
            ):
                continue
            return absolute
        except ValueError:
            continue
    return None
