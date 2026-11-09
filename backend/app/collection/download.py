"""Bounded HTTP requests pinned to validated public IP addresses."""

import asyncio
import ipaddress
import json
import socket
import sys
import zlib
from asyncio import create_subprocess_exec
from collections.abc import Callable
from dataclasses import dataclass
from threading import Thread
from time import monotonic

import httpx

from app.config import Settings

# Isolated Python, standard library only, no inherited environment or application imports.
# Host and port are separate arguments, never interpolated into executable code.
_DNS_SCRIPT = """
import json, socket, sys
try:
    rows = socket.getaddrinfo(sys.argv[1], int(sys.argv[2]), type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(row[4][0] for row in rows))
    if len(addresses) > 64:
        raise ValueError()
    print(json.dumps(addresses))
except (OSError, ValueError):
    sys.exit(1)
"""


async def resolve_public_host_bounded(host: str, port: int, timeout: float) -> str:
    """Kill and reap slow OS DNS resolution before allowing the next feed."""
    process = None
    try:
        async with asyncio.timeout(timeout):
            process = await create_subprocess_exec(
                sys.executable,
                "-I",
                "-S",
                "-c",
                _DNS_SCRIPT,
                host,
                str(port),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env={},
            )
            output, _ = await process.communicate()
        if process.returncode != 0:
            raise FeedError("Feed hostname could not be resolved")
        addresses = json.loads(output)
        if not addresses or not all(public_address(address) for address in addresses):
            raise FeedError("Feed destination must resolve only to public IP addresses")
        return addresses[0]
    except TimeoutError as exc:
        raise FeedError("Feed hostname resolution timed out") from exc
    except (OSError, ValueError) as exc:
        raise FeedError("Feed hostname could not be resolved") from exc
    finally:
        if process is not None and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()


class FeedError(Exception):
    """A safe, user-facing collection error. Never include raw response bodies or URLs."""


@dataclass(frozen=True)
class Download:
    body: bytes
    url: str
    not_modified: bool = False
    etag: str | None = None
    last_modified: str | None = None


def public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    # Block transition mechanisms too: they can encode a different IPv4 destination.
    return (
        address.is_global
        and not address.is_multicast
        and not address.is_reserved
        and not getattr(address, "ipv4_mapped", None)
        and not getattr(address, "sixtofour", None)
        and not getattr(address, "teredo", None)
        and "%" not in value
    )


def resolve_public_host(host: str, port: int) -> str:
    try:
        addresses = [item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]
    except OSError as exc:
        raise FeedError("Feed hostname could not be resolved") from exc
    if not addresses or not all(public_address(address) for address in addresses):
        raise FeedError("Feed destination must resolve only to public IP addresses")
    return addresses[0]


def checked_url(value: str) -> httpx.URL:
    try:
        url = httpx.URL(value)
        if (
            url.scheme not in {"http", "https"}
            or not url.host
            or url.userinfo
            or url.fragment
            or url.port not in {None, 80, 443}
            or len(str(url)) > 2048
        ):
            raise ValueError
        return url
    except (ValueError, httpx.InvalidURL) as exc:
        raise FeedError(
            "Feed URL must use HTTP/HTTPS on port 80 or 443 without credentials or fragments"
        ) from exc


def cache_header(value: str | None) -> str | None:
    if value and len(value) <= 1024 and all(32 <= ord(char) < 127 for char in value):
        return value
    return None


class FeedDownloader:
    def __init__(
        self,
        settings: Settings,
        *,
        resolver: Callable[[str, int], str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.resolver = resolver
        self.transport = transport

    def fetch(
        self,
        value: str,
        etag: str | None,
        last_modified: str | None,
        *,
        deadline: float | None = None,
    ) -> Download:
        # Sync API routes run outside an event loop. A few direct callers (including
        # tests) already have one; bridge them without nesting asyncio.run().
        async def bounded():
            seconds = min(30, self.settings.feed_timeout_seconds * 3)
            if deadline is not None:
                seconds = min(seconds, deadline - monotonic())
            if seconds <= 0:
                raise FeedError("Feed download exceeded its time budget")
            try:
                async with asyncio.timeout(seconds):
                    return await self._fetch(value, etag, last_modified, deadline=deadline)
            except TimeoutError as exc:
                raise FeedError("Feed download exceeded its time budget") from exc

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(bounded())
        outcome = []

        def run():
            try:
                outcome.append(asyncio.run(bounded()))
            except Exception as exc:
                outcome.append(exc)

        worker = Thread(target=run, name="feed-download")
        worker.start()
        worker.join()
        if isinstance(outcome[0], Exception):
            raise outcome[0]
        return outcome[0]

    async def _fetch(
        self,
        value: str,
        etag: str | None,
        last_modified: str | None,
        *,
        deadline: float | None = None,
    ) -> Download:
        url = checked_url(value)
        conditional = {}
        if cached := cache_header(etag):
            conditional["If-None-Match"] = cached
        if cached := cache_header(last_modified):
            conditional["If-Modified-Since"] = cached
        deadline = min(
            deadline if deadline is not None else float("inf"),
            monotonic() + min(30, self.settings.feed_timeout_seconds * 3),
        )
        try:
            # A fresh client per hop prevents cookies and TLS connections crossing origins.
            for hop in range(4):
                hostname = url.raw_host.decode("ascii")
                port = url.port or (443 if url.scheme == "https" else 80)
                address = (
                    # Explicit synchronous resolver injection is reserved for offline tests.
                    self.resolver(hostname, port)
                    if self.resolver is not None
                    else await resolve_public_host_bounded(
                        hostname,
                        port,
                        min(10, self.settings.feed_timeout_seconds, deadline - monotonic()),
                    )
                )
                if not public_address(address):
                    raise FeedError("Feed destination is not a public IP address")
                if monotonic() >= deadline:
                    raise FeedError("Feed download exceeded its time budget")
                target = url.copy_with(host=address)
                headers = {
                    "Host": url.netloc.decode("ascii"),
                    "User-Agent": "TechNewsRadar/0.1",
                    "Accept": "application/atom+xml, application/rss+xml, application/xml",
                    # Prefer identity, but handle servers that always send gzip with strict limits.
                    "Accept-Encoding": "identity",
                    **conditional,
                }
                async with httpx.AsyncClient(
                    transport=self.transport,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=min(10, self.settings.feed_timeout_seconds, deadline - monotonic()),
                ) as client:
                    async with client.stream(
                        "GET", target, headers=headers, extensions={"sni_hostname": hostname}
                    ) as response:
                        if monotonic() >= deadline:
                            raise FeedError("Feed download exceeded its time budget")
                        if response.status_code in {301, 302, 303, 307, 308}:
                            if hop == 3 or "location" not in response.headers:
                                raise FeedError("Feed redirect limit exceeded or target missing")
                            next_url = checked_url(str(url.join(response.headers["location"])))
                            if url.scheme == "https" and next_url.scheme != "https":
                                raise FeedError("HTTPS feeds cannot redirect to HTTP")
                            # Validators identify the configured resource. Re-fetch after redirects.
                            conditional = {}
                            url = next_url
                            continue
                        if response.status_code == 304:
                            if not conditional:
                                raise FeedError("Feed returned an unexpected HTTP 304")
                            return Download(
                                b"",
                                str(url),
                                True,
                                cache_header(response.headers.get("etag")) or cache_header(etag),
                                cache_header(response.headers.get("last-modified"))
                                or cache_header(last_modified),
                            )
                        if response.status_code != 200:
                            raise FeedError(f"Feed server returned HTTP {response.status_code}")
                        encoding = response.headers.get("content-encoding", "identity").lower()
                        if encoding not in {"identity", "gzip"}:
                            raise FeedError("Feed uses an unsupported content encoding")
                        decoder = (
                            zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == "gzip" else None
                        )
                        length = response.headers.get("content-length")
                        if (
                            length
                            and length.isdecimal()
                            and int(length) > self.settings.feed_max_bytes
                        ):
                            raise FeedError("Feed exceeds the download size limit")
                        body = bytearray()
                        received = 0
                        async for chunk in response.aiter_raw():
                            if monotonic() >= deadline:
                                raise FeedError("Feed download exceeded its time budget")
                            received += len(chunk)
                            if received > self.settings.feed_max_bytes:
                                raise FeedError("Feed exceeds the download size limit")
                            if decoder is not None:
                                try:
                                    chunk = decoder.decompress(
                                        chunk, self.settings.feed_max_bytes - len(body) + 1
                                    )
                                except zlib.error as exc:
                                    raise FeedError("Feed contains invalid gzip data") from exc
                                if decoder.unused_data:
                                    raise FeedError(
                                        "Feed contains trailing or concatenated gzip data"
                                    )
                            if len(body) + len(chunk) > self.settings.feed_max_bytes:
                                raise FeedError("Feed exceeds the decoded size limit")
                            body.extend(chunk)
                        if decoder is not None and not decoder.eof:
                            raise FeedError("Feed contains incomplete gzip data")
                        if monotonic() >= deadline:
                            raise FeedError("Feed download exceeded its time budget")
                        return Download(
                            bytes(body),
                            str(url),
                            False,
                            cache_header(response.headers.get("etag")) if hop == 0 else None,
                            cache_header(response.headers.get("last-modified"))
                            if hop == 0
                            else None,
                        )
        except httpx.TimeoutException as exc:
            raise FeedError("Feed request timed out") from exc
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            raise FeedError("Feed HTTP request failed") from exc
        raise FeedError("Feed redirect limit exceeded")
