"""Bounded HTTP requests pinned to validated public IP addresses."""

import ipaddress
import socket
import time
import zlib
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from app.config import Settings


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
        resolver: Callable[[str, int], str] = resolve_public_host,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.resolver = resolver
        self.transport = transport

    def fetch(self, value: str, etag: str | None, last_modified: str | None) -> Download:
        url = checked_url(value)
        conditional = {}
        if cached := cache_header(etag):
            conditional["If-None-Match"] = cached
        if cached := cache_header(last_modified):
            conditional["If-Modified-Since"] = cached
        deadline = time.monotonic() + self.settings.feed_timeout_seconds * 3
        try:
            # A fresh client per hop prevents cookies and TLS connections crossing origins.
            for hop in range(4):
                hostname = url.raw_host.decode("ascii")
                address = self.resolver(
                    hostname, url.port or (443 if url.scheme == "https" else 80)
                )
                if not public_address(address):
                    raise FeedError("Feed destination is not a public IP address")
                if time.monotonic() >= deadline:
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
                with httpx.Client(
                    transport=self.transport,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=self.settings.feed_timeout_seconds,
                ) as client:
                    with client.stream(
                        "GET", target, headers=headers, extensions={"sni_hostname": hostname}
                    ) as response:
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
                        for chunk in response.iter_raw(chunk_size=65536):
                            if time.monotonic() >= deadline:
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
