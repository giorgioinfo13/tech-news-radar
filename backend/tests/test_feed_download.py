import gzip
import socket

import httpx
import pytest

from app.collection.download import FeedDownloader, FeedError, resolve_public_host
from app.config import Settings

PUBLIC_IP = "93.184.215.14"


def downloader(handler, **settings):
    return FeedDownloader(
        Settings(_env_file=None, **settings),
        resolver=lambda host, port: PUBLIC_IP,
        transport=httpx.MockTransport(handler),
    )


def test_pinned_destination_host_sni_and_conditional_headers(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")

    def handle(request):
        assert request.url.host == PUBLIC_IP
        assert request.url.path == "/feed"
        assert request.headers["host"] == "example.org"
        assert request.extensions["sni_hostname"] == "example.org"
        assert request.headers["if-none-match"] == '"v1"'
        assert request.headers["if-modified-since"] == "Thu, 01 Jan 2026 00:00:00 GMT"
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(304, headers={"etag": '"v2"'})

    result = downloader(handle).fetch(
        "https://example.org/feed", '"v1"', "Thu, 01 Jan 2026 00:00:00 GMT"
    )
    assert result.not_modified
    assert result.etag == '"v2"'
    assert result.body == b""


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "0.0.0.0",
        "100.64.0.1",
        "224.0.0.1",
        "::1",
        "fe80::1",
        "fc00::1",
        "::ffff:127.0.0.1",
        "2002:7f00:1::",
        "64:ff9b::7f00:1",
    ],
)
def test_private_and_special_dns_answers_rejected(monkeypatch, address):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *args, **kwargs: [(0, 0, 0, "", (address, 443))]
    )
    with pytest.raises(FeedError, match="public"):
        resolve_public_host("example.org", 443)


def test_mixed_dns_answers_and_dns_errors_rejected(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (0, 0, 0, "", (PUBLIC_IP, 443)),
            (0, 0, 0, "", ("127.0.0.1", 443)),
        ],
    )
    with pytest.raises(FeedError):
        resolve_public_host("example.org", 443)

    def failed(*args, **kwargs):
        raise socket.gaierror("private diagnostic")

    monkeypatch.setattr(socket, "getaddrinfo", failed)
    with pytest.raises(FeedError, match="could not be resolved"):
        resolve_public_host("example.org", 443)


def test_redirects_revalidate_destination_and_do_not_reuse_validators():
    requests, hosts = [], []

    def resolve(host, port):
        hosts.append(host)
        return PUBLIC_IP if host == "example.org" else "127.0.0.1"

    def handle(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": "https://localhost/private"})

    fetcher = downloader(handle)
    fetcher.resolver = resolve
    with pytest.raises(FeedError, match="public"):
        fetcher.fetch("https://example.org/feed", None, None)
    assert hosts == ["example.org", "localhost"]
    assert len(requests) == 1


def test_public_redirect_relative_resolution_and_cache_is_not_shared():
    requests = []

    def handle(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(301, headers={"location": "/new", "set-cookie": "secret=1"})
        assert "if-none-match" not in request.headers
        assert "cookie" not in request.headers
        return httpx.Response(200, headers={"etag": '"other"'}, stream=httpx.ByteStream(b"<rss/>"))

    result = downloader(handle).fetch("https://example.org/feed", '"old"', None)
    assert result.url == "https://example.org/new"
    assert result.body == b"<rss/>"
    assert result.etag is None


@pytest.mark.parametrize(
    "target",
    [
        "http://example.org/plain",
        "file:///etc/passwd",
        "https://user:pass@example.org/feed",
        "https://example.org:8080/feed",
        "https://example.org/feed#fragment",
    ],
)
def test_unsafe_redirects_rejected(target):
    with pytest.raises(FeedError):
        downloader(lambda request: httpx.Response(302, headers={"location": target})).fetch(
            "https://example.org/feed", None, None
        )


def test_redirect_loop_is_bounded():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": "/loop"})

    with pytest.raises(FeedError, match="redirect limit"):
        downloader(handle).fetch("https://example.org/feed", None, None)
    assert len(requests) == 4


@pytest.mark.parametrize(
    "response, message",
    [
        (lambda: httpx.Response(503), "HTTP 503"),
        (lambda: httpx.Response(304), "unexpected HTTP 304"),
        (lambda: httpx.Response(200, headers={"content-length": "5000"}), "size limit"),
        (lambda: httpx.Response(200, stream=httpx.ByteStream(b"x" * 1025)), "size limit"),
        (lambda: httpx.Response(200, headers={"content-encoding": "br"}), "unsupported"),
    ],
)
def test_http_failures_and_size_limits(response, message):
    with pytest.raises(FeedError, match=message):
        downloader(lambda request: response(), feed_max_bytes=1024).fetch(
            "https://example.org", None, None
        )


@pytest.mark.parametrize("error", [httpx.ReadTimeout, httpx.ConnectError])
def test_network_errors_do_not_leak_urls(error):
    def handle(request):
        raise error("https://example.org/?token=secret")

    with pytest.raises(FeedError) as exc:
        downloader(handle).fetch("https://example.org", None, None)
    assert "secret" not in str(exc.value)


def test_international_hostname_uses_ascii_for_dns_and_tls():
    hosts = []

    def resolve(host, port):
        hosts.append(host)
        return PUBLIC_IP

    def handle(request):
        assert request.headers["host"] == "xn--fsqu00a.com"
        assert request.extensions["sni_hostname"] == "xn--fsqu00a.com"
        return httpx.Response(200, stream=httpx.ByteStream(b"<rss/>"))

    fetcher = downloader(handle)
    fetcher.resolver = resolve
    fetcher.fetch("https://例子.com/rss", None, None)
    assert hosts == ["xn--fsqu00a.com"]


def test_size_limit_accumulates_streamed_chunks_and_closes_stream():
    closed = []

    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"x" * 600
            yield b"x" * 600

        async def aclose(self):
            closed.append(True)

    with pytest.raises(FeedError, match="size limit"):
        downloader(lambda request: httpx.Response(200, stream=Chunks()), feed_max_bytes=1024).fetch(
            "https://example.org/feed", None, None
        )
    assert closed == [True]


def test_body_stream_deadline(monkeypatch):
    clock = [0]
    monkeypatch.setattr("app.collection.download.monotonic", lambda: clock[0])

    class LateBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            clock[0] = 31
            yield b"<rss/>"

    with pytest.raises(FeedError, match="time budget"):
        downloader(lambda request: httpx.Response(200, stream=LateBody())).fetch(
            "https://example.org", None, None
        )


def gzip_response(body):
    return httpx.Response(200, headers={"content-encoding": "gzip"}, stream=httpx.ByteStream(body))


def test_gzip_content_at_decoded_limit():
    body = b"x" * 1024
    result = downloader(
        lambda request: gzip_response(gzip.compress(body)), feed_max_bytes=1024
    ).fetch("https://example.org/feed", None, None)
    assert result.body == body


@pytest.mark.parametrize(
    "body, message",
    [
        (gzip.compress(b"x" * 1_000_000), "decoded size limit"),
        (gzip.compress(b"hello")[:-1], "incomplete gzip"),
        (b"not gzip", "invalid gzip"),
        (gzip.compress(b"hello") + b"trailing", "trailing"),
        (gzip.compress(b"hello") + gzip.compress(b"world"), "concatenated"),
    ],
)
def test_invalid_or_excessive_gzip_is_rejected(body, message):
    with pytest.raises(FeedError, match=message):
        downloader(lambda request: gzip_response(body), feed_max_bytes=1024).fetch(
            "https://example.org/feed", None, None
        )


def test_absolute_timeout_cancels_slow_headers_and_closes_transport():
    import asyncio
    from time import monotonic

    closed = []

    class SlowHeaders(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            await asyncio.sleep(60)
            raise AssertionError("Timed-out request resumed")

        async def aclose(self):
            closed.append(True)

    fetcher = FeedDownloader(
        Settings(feed_timeout_seconds=0.02),
        resolver=lambda *args: PUBLIC_IP,
        transport=SlowHeaders(),
    )
    started = monotonic()
    with pytest.raises(FeedError, match="time budget"):
        fetcher.fetch("https://example.org/feed", None, None)
    assert monotonic() - started < 1
    assert closed == [True]


def test_absolute_timeout_cancels_slow_body_without_waiting_for_a_full_chunk():
    import asyncio
    from time import monotonic

    closed = []

    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            while True:
                await asyncio.sleep(0.01)
                yield b"x"

        async def aclose(self):
            closed.append(True)

    fetcher = downloader(
        lambda request: httpx.Response(200, stream=SlowBody()), feed_timeout_seconds=0.02
    )
    started = monotonic()
    with pytest.raises(FeedError, match="time budget"):
        fetcher.fetch("https://example.org/feed", None, None)
    assert monotonic() - started < 1
    assert closed == [True]


@pytest.mark.anyio
async def test_stuck_dns_is_killed_and_next_resolution_can_succeed(monkeypatch):
    import asyncio

    from app.collection import download

    processes = []

    class DNSProcess:
        returncode = None
        killed = False
        reaped = False

        async def communicate(self):
            if len(processes) == 1:
                await asyncio.sleep(60)
            self.returncode = 0
            return b'["93.184.215.14"]', b""

        def kill(self):
            self.killed = True
            self.returncode = -9

        async def wait(self):
            self.reaped = True

    async def spawn(*args, **kwargs):
        assert args[-2:] == ("example.org", "443")
        assert kwargs["env"] == {}
        process = DNSProcess()
        processes.append(process)
        return process

    monkeypatch.setattr(download, "create_subprocess_exec", spawn)
    with pytest.raises(FeedError, match="resolution timed out"):
        await download.resolve_public_host_bounded("example.org", 443, 0.02)
    assert processes[0].killed and processes[0].reaped
    assert await download.resolve_public_host_bounded("example.org", 443, 1) == PUBLIC_IP
    assert len(processes) == 2


@pytest.mark.anyio
async def test_dns_worker_start_failure_does_not_leave_a_lock(monkeypatch):
    from app.collection import download

    async def cannot_start(*args, **kwargs):
        raise OSError("Cannot start a new process")

    monkeypatch.setattr(download, "create_subprocess_exec", cannot_start)
    for _ in range(2):
        with pytest.raises(FeedError, match="could not be resolved"):
            await download.resolve_public_host_bounded("example.org", 443, 1)


@pytest.mark.anyio
async def test_isolated_dns_process_resolves_numeric_address_without_network(monkeypatch):
    import asyncio

    from app.collection import download

    # A numeric address is resolved locally by libc, without a DNS/provider request.
    monkeypatch.setattr(download, "create_subprocess_exec", asyncio.create_subprocess_exec)
    assert await download.resolve_public_host_bounded(PUBLIC_IP, 443, 2) == PUBLIC_IP
    with pytest.raises(FeedError, match="public"):
        await download.resolve_public_host_bounded("127.0.0.1", 443, 2)
