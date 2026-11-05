from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.collection.download import FeedError
from app.collection.parsing import parse_feed, url_key

FIXTURES = Path(__file__).parent / "fixtures"


def test_rss_dates_plain_text_relative_links_and_invalid_entry():
    result = parse_feed((FIXTURES / "rss.xml").read_bytes(), "https://example.org/feed", 100)
    assert result.seen == 3
    assert len(result.entries) == 2
    first, second = result.entries
    assert first.guid == "first"
    assert first.title == "First & useful"
    assert first.description == "Hello world. Next line."
    assert first.url == "https://example.org/first?original=1#section"
    assert first.published_at == datetime(2026, 1, 1, 8, tzinfo=UTC)
    assert second.published_at is None
    assert second.url == "https://example.org/second"


def test_atom_published_is_distinct_from_updated():
    result = parse_feed((FIXTURES / "atom.xml").read_bytes(), "https://example.org/feed", 100)
    assert result.seen == 2
    first, second = result.entries
    assert first.guid == "urn:example:one"
    assert first.url == "https://example.org/blog/article"
    assert first.description == "An Atom summary"
    assert first.published_at == datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    assert second.published_at is None


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"not XML",
        b"<rss><channel>",
        b"<html><body>Not a feed</body></html>",
        b'<!DOCTYPE rss [<!ENTITY x SYSTEM "file:///etc/passwd">]><rss>&x;</rss>',
        b'<!DOCTYPE rss SYSTEM "https://private.invalid/dtd"><rss/>',
        b'<rss version="2.0"><channel><item><title>Missing link</title></item></channel></rss>',
        b'<rss version="2.0"><channel><item><title>Bad</title><link>file:///etc/passwd</link></item></channel></rss>',
        b"<rss>" + b"<x>" * 65 + b"</x>" * 65 + b"</rss>",
    ],
)
def test_invalid_and_unsafe_documents_are_rejected(body):
    with pytest.raises(FeedError):
        parse_feed(body, "https://example.org/feed", 100)


def test_empty_feed_is_valid_and_large_feed_is_rejected():
    assert (
        parse_feed(
            b'<rss version="2.0"><channel><title>Empty</title></channel></rss>',
            "https://example.org",
            10,
        ).entries
        == []
    )
    with pytest.raises(FeedError, match="entry limit"):
        parse_feed((FIXTURES / "rss.xml").read_bytes(), "https://example.org", 1)


def test_url_identity_is_conservative():
    assert url_key("HTTPS://EXAMPLE.ORG:443/a?utm=1#one") == url_key(
        "https://example.org/a?utm=1#two"
    )
    assert url_key("https://example.org/a?utm=1") != url_key("https://example.org/a?utm=2")
