"""Wake Render and request one scan. Standard library only; never print credentials."""

import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_RESPONSE_BYTES = 32768
FAILURE_REASONS = {
    "timeout",
    "dns_error",
    "network_error",
    "unsafe_destination",
    "redirect_error",
    "unexpected_304",
    "size_limit",
    "encoding_error",
    "invalid_feed",
    "unexpected_error",
}


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # In particular, never forward the collection credential to another origin.
        return None


def read_json(opener, request, timeout):
    with opener.open(request, timeout=timeout) as response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise ValueError("Response too large")
        if response.status != 200:
            raise ValueError("Unexpected response status")
        return json.loads(body)


def log_failures(result):
    # Optional for compatibility with the backend before its next deployment.
    failures = result.get("failures")
    if failures is None:
        if result["failed"]:
            print("::warning::Source diagnostics unavailable; inspect backend collection history.")
        return
    if not isinstance(failures, list) or len(failures) != result["failed"] or len(failures) > 100:
        raise ValueError("Invalid failure diagnostics")
    for failure in failures:
        if not isinstance(failure, dict):
            raise TypeError("Invalid failure diagnostics")
        source_id, run_id, reason = (
            failure.get("source_id"),
            failure.get("run_id"),
            failure.get("reason"),
        )
        if (
            type(source_id) is not int
            or not 0 < source_id <= 2**63 - 1
            or (run_id is not None and (type(run_id) is not int or not 0 < run_id <= 2**63 - 1))
            or not isinstance(reason, str)
            or (reason not in FAILURE_REASONS and not re.fullmatch(r"http_[1-5][0-9]{2}", reason))
        ):
            raise ValueError("Invalid failure diagnostics")
    # Validate the whole list before emitting annotations. No server-controlled prose is printed.
    for failure in failures:
        print(
            f"::error::Collection failed: source_id={failure['source_id']}, "
            f"run_id={failure['run_id']}, reason={failure['reason']}"
        )


def main() -> int:
    origin = os.environ.get("TNR_BACKEND_URL", "").rstrip("/")
    secret = os.environ.get("TNR_COLLECTION_TRIGGER_SECRET", "")
    if not re.fullmatch(r"https://[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.onrender\.com", origin):
        print("Set TNR_BACKEND_URL to the exact HTTPS onrender.com backend origin.")
        return 1
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", secret):
        print("Set a valid collection trigger secret.")
        return 1

    opener = build_opener(NoRedirects())
    # Wake the service without sending the secret. Allow a bounded cold-start delay.
    for attempt in range(12):
        try:
            health = read_json(opener, Request(origin + "/api/health"), timeout=10)
            if health == {"status": "ok"}:
                break
        except HTTPError as exc:
            if exc.code < 500:
                print(f"Health check refused (HTTP {exc.code}); no collection requested.")
                return 1
        except (URLError, OSError, ValueError):
            pass
        if attempt == 11:
            print("Backend did not become ready within the cold-start retry budget.")
            return 1
        time.sleep(5)

    request = Request(
        origin + "/api/internal/collect",
        data=b"",
        headers={"Authorization": "Bearer " + secret},
        method="POST",
    )
    try:
        result = read_json(opener, request, timeout=600)
    except HTTPError as exc:
        if exc.code in (409, 429):
            print(f"::warning::Collection deferred (HTTP {exc.code}); scan or cooldown active.")
            return 0
        print(f"Collection request failed (HTTP {exc.code}).")
        return 1
    except (URLError, OSError, ValueError):
        # A timed-out POST may still be running. Do not blindly submit a second scan.
        print("Collection completion could not be confirmed; POST was not retried.")
        return 1

    counts = ("collected", "failed", "skipped")
    if (
        not isinstance(result, dict)
        or any(type(result.get(key)) is not int or result[key] < 0 for key in counts)
        or type(result.get("deferred")) is not bool
    ):
        print("Invalid collection result; completion could not be confirmed.")
        return 1
    # Print only validated counts, never raw server bodies, headers, or exceptions.
    print("Collection: " + ", ".join(f"{key}={result[key]}" for key in (*counts, "deferred")))
    try:
        log_failures(result)
    except (TypeError, ValueError):
        print("Invalid failure diagnostics; inspect backend collection history.")
        return 1
    if result["deferred"]:
        print("::warning::Collection deferred: remaining sources will be reconsidered next scan.")
    return int(result["failed"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
