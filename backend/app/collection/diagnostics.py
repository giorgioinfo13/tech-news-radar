"""Content-free failure codes for operator scan results."""

import re

_REASONS = {
    "timeout": {
        "Feed hostname resolution timed out",
        "Feed download exceeded its time budget",
        "Feed request timed out",
    },
    "dns_error": {"Feed hostname could not be resolved"},
    "network_error": {"Feed HTTP request failed"},
    "unsafe_destination": {
        "Feed destination must resolve only to public IP addresses",
        "Feed destination is not a public IP address",
        "Feed URL must use HTTP/HTTPS on port 80 or 443 without credentials or fragments",
        "HTTPS feeds cannot redirect to HTTP",
    },
    "redirect_error": {
        "Feed redirect limit exceeded or target missing",
        "Feed redirect limit exceeded",
    },
    "unexpected_304": {"Feed returned an unexpected HTTP 304"},
    "size_limit": {
        "Feed exceeds the download size limit",
        "Feed exceeds the decoded size limit",
        "Feed exceeds the entry limit",
        "Feed XML exceeds the nesting limit",
    },
    "encoding_error": {
        "Feed uses an unsupported content encoding",
        "Feed contains invalid gzip data",
        "Feed contains trailing or concatenated gzip data",
        "Feed contains incomplete gzip data",
    },
    "invalid_feed": {
        "Feed is not valid XML or contains prohibited XML declarations",
        "Document is not an RSS or Atom feed",
        "Feed contains no usable entries with a title and HTTP/HTTPS link",
    },
}


def failure_reason(message: str | None) -> str:
    """Allow only known messages, never URLs, response bodies, or exception text."""
    match = re.fullmatch(r"Feed server returned HTTP ([1-5][0-9]{2})", message or "")
    if match:
        return "http_" + match[1]
    for code, messages in _REASONS.items():
        if message in messages:
            return code
    return "unexpected_error"
