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


@pytest.mark.parametrize(
    "comments, expected",
    [
        ("https://news.ycombinator.com/item?id=123", "https://news.ycombinator.com/item?id=123"),
        ("https://evil.example/item?id=123", None),
        ("javascript:alert(1)", None),
        ("https://news.ycombinator.com.evil.example/item?id=123", None),
    ],
)
def test_hacker_news_discussion_is_separate_and_validated(comments, expected):
    body = f'''<rss version="2.0"><channel><item><title>News</title>
    <link>https://example.org/article</link><comments>{comments}</comments>
    <description><![CDATA[<a href="{comments}">Comments</a>]]></description>
    </item></channel></rss>'''.encode()
    entry = parse_feed(body, "https://news.ycombinator.com/rss", 10).entries[0]
    assert entry.discussion_url == expected
    assert entry.description is None
    other = parse_feed(body, "https://example.org/rss", 10).entries[0]
    assert other.discussion_url is None
    assert other.description == "Comments"


@pytest.mark.parametrize(
    "source, fields, expected",
    [
        (
            "https://research.google/blog/rss/",
            '<media:thumbnail url="https://storage.googleapis.com/test/preview.jpg"/>'
            '<media:content medium="image" url="https://storage.googleapis.com/test/full.jpg"/>',
            "https://storage.googleapis.com/test/preview.jpg",
        ),
        (
            "https://research.google/blog/rss/",
            '<media:thumbnail url="https://elsewhere.example/tracker"/>'
            '<media:content type="image/png" url="https://storage.googleapis.com/test/full.png"/>',
            "https://storage.googleapis.com/test/full.png",
        ),
        (
            "https://www.hdblog.it/feed/",
            "<thumb>https://hd2.tudocdn.net/image?w=180</thumb>",
            "https://hd2.tudocdn.net/image?w=180",
        ),
        (
            "https://andreagaleazzi.com/feed/",
            "<image>https://andreagaleazzi.com/article.jpg</image>",
            "https://andreagaleazzi.com/article.jpg",
        ),
        (
            "https://blog.cloudflare.com/rss/",
            '<enclosure type="image/jpeg" url="https://blog.cloudflare.com/thumbnail.jpg"/>',
            "https://blog.cloudflare.com/thumbnail.jpg",
        ),
        (
            "https://blog.cloudflare.com/rss/",
            '<enclosure type="video/mp4" url="https://blog.cloudflare.com/movie.mp4"/>',
            None,
        ),
        (
            "https://research.google/blog/rss/",
            '<media:thumbnail url="https://user@storage.googleapis.com/a"/>'
            '<media:thumbnail url="http://storage.googleapis.com/a"/>'
            '<media:thumbnail url="https://storage.googleapis.com:8000/a"/>',
            None,
        ),
        (
            "https://github.com/openai/codex/releases.atom",
            '<media:thumbnail url="https://avatars.githubusercontent.com/u/1"/>',
            None,
        ),
        (
            "https://www.youtube.com/feeds/videos.xml?channel_id=other",
            '<media:thumbnail url="https://i1.ytimg.com/thumb.jpg"/>',
            None,
        ),
        (
            "https://importai.substack.com/feed",
            '<enclosure type="image/png" url="https://substackcdn.com/resized/logo.png"/>',
            None,
        ),
    ],
)
def test_thumbnails_use_only_supported_item_fields(source, fields, expected):
    body = f"""<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel>
    <image><url>https://substackcdn.com/original/logo.png</url></image>
    <item><title>Article</title><link>https://example.org/post</link>
    <description><![CDATA[<img src="https://storage.googleapis.com/inline.png">]]></description>
    {fields}</item></channel></rss>""".encode()
    assert parse_feed(body, source, 5).entries[0].thumbnail_url == expected
