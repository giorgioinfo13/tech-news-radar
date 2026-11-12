import pytest

from app.collection.diagnostics import failure_reason


@pytest.mark.parametrize(
    "message, expected",
    [
        ("Feed server returned HTTP 403", "http_403"),
        ("Feed server returned HTTP 503", "http_503"),
        ("Feed request timed out", "timeout"),
        ("Feed hostname could not be resolved", "dns_error"),
        ("Feed HTTP request failed", "network_error"),
        ("Feed destination is not a public IP address", "unsafe_destination"),
        ("Feed redirect limit exceeded", "redirect_error"),
        ("Feed returned an unexpected HTTP 304", "unexpected_304"),
        ("Feed exceeds the decoded size limit", "size_limit"),
        ("Feed contains invalid gzip data", "encoding_error"),
        ("Document is not an RSS or Atom feed", "invalid_feed"),
        ("https://example.org/?token=private", "unexpected_error"),
        ("Feed server returned HTTP 503\nprivate", "unexpected_error"),
        (None, "unexpected_error"),
    ],
)
def test_only_known_content_free_failure_reasons_are_exposed(message, expected):
    assert failure_reason(message) == expected
