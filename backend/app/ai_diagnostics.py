"""Small allowlisted diagnostics, never raw provider payloads or request headers."""

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from math import ceil


def retry_after(value: str | None, now: datetime) -> tuple[int | None, str]:
    if value is None:
        return None, "absent"
    value = value.strip()
    if value.isascii() and value.isdigit() and len(value) <= 7:
        return int(value), "seconds"
    if len(value) <= 100:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is not None:
                seconds = max(0, ceil((date - now).total_seconds()))
                if seconds <= 9_999_999:
                    return seconds, "http_date"
        except (ValueError, TypeError, OverflowError):
            pass
    return None, "unparsed"


def provider_diagnostics(
    status: int, retry_header: str | None, *, now: datetime | None = None
) -> dict:
    """Return fixed labels and numeric fields only; omit unknown external strings."""
    seconds, kind = retry_after(retry_header, now or datetime.now(UTC))
    result = {"http_status": status, "retry_after_kind": kind}
    if seconds is not None:
        result["retry_after_seconds"] = seconds
    return result
