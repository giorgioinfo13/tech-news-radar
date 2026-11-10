"""Parse bytes only; feedparser never receives a URL or a filesystem path."""

import calendar
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from io import BytesIO
from urllib.parse import urljoin
from xml.etree.ElementTree import ParseError

import feedparser
import httpx
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import iterparse

from app.collection.download import FeedError


class PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        elif tag in {"p", "br", "div", "li"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.hidden:
            self.hidden -= 1
        elif tag in {"p", "div", "li"}:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(value: str, limit: int) -> str:
    parser = PlainText()
    parser.feed(value)
    parser.close()
    return " ".join("".join(parser.parts).split())[:limit]


def article_url(value: str, base: str) -> str | None:
    try:
        absolute = urljoin(base, value.strip())
        parsed = httpx.URL(absolute)
    except (ValueError, httpx.InvalidURL):
        return None
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.host
        or parsed.userinfo
        or len(absolute) > 2048
        or any(ord(char) < 32 for char in absolute)
    ):
        return None
    # Preserve the publisher's link, including query and fragment. Never download it.
    return absolute


def url_key(value: str) -> str:
    return str(httpx.URL(value).copy_with(fragment=None))


@dataclass(frozen=True)
class Entry:
    guid: str | None
    url: str
    title: str
    description: str | None
    published_at: datetime | None
    discussion_url: str | None = None


@dataclass(frozen=True)
class ParsedFeed:
    entries: list[Entry]
    seen: int


def parse_feed(body: bytes, base_url: str, max_entries: int) -> ParsedFeed:
    try:
        depth = 0
        for event, element in iterparse(
            BytesIO(body),
            events=("start", "end"),
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        ):
            depth += 1 if event == "start" else -1
            if depth > 64:
                raise FeedError("Feed XML exceeds the nesting limit")
            if event == "end":
                element.clear()
    except (ParseError, DefusedXmlException, ValueError) as exc:
        raise FeedError("Feed is not valid XML or contains prohibited XML declarations") from exc
    parsed = feedparser.parse(BytesIO(body), response_headers={"content-location": base_url})
    if not parsed.version or not parsed.version.startswith(("rss", "atom")):
        raise FeedError("Document is not an RSS or Atom feed")
    if len(parsed.entries) > max_entries:
        raise FeedError("Feed exceeds the entry limit")
    entries = []
    for item in parsed.entries:
        title = plain_text(item.get("title", ""), 1000)
        link = item.get("link", "")
        url = article_url(link, base_url) if link else None
        guid = item.get("id", "").strip() or None
        if not title or not url or (guid and len(guid) > 1024):
            continue
        published = None
        # Do not use 'updated' as a substitute for an unknown publication date.
        if date := item.get("published_parsed"):
            try:
                published = datetime.fromtimestamp(calendar.timegm(date), UTC)
            except (ValueError, OverflowError, OSError):
                pass
        summary = item.get("summary", "")
        if not summary and item.get("content"):
            summary = item.content[0].get("value", "")
        description = plain_text(summary, 4000) or None
        discussion = None
        if httpx.URL(base_url).host == "news.ycombinator.com":
            comments = item.get("comments", "")
            if re.fullmatch(r"https://news\.ycombinator\.com/item\?id=[1-9][0-9]*", comments):
                discussion = comments
            if description == "Comments":
                description = None
        entries.append(Entry(guid, url, title, description, published, discussion))
    if parsed.entries and not entries:
        raise FeedError("Feed contains no usable entries with a title and HTTP/HTTPS link")
    return ParsedFeed(entries, len(parsed.entries))
