"""Wake Render and request one hourly digest. Standard library only; never print credentials."""

import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # In particular, never forward the digest credential to another origin.
        return None


def read_json(opener, request, timeout):
    with opener.open(request, timeout=timeout) as response:
        body = response.read(8193)
        if len(body) > 8192:
            raise ValueError("Response too large")
        if response.status != 200:
            raise ValueError("Unexpected response status")
        return json.loads(body)


def main() -> int:
    origin = os.environ.get("TNR_BACKEND_URL", "").rstrip("/")
    secret = os.environ.get("TNR_AI_DIGEST_TRIGGER_SECRET", "")
    if not re.fullmatch(
        r"https://[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.onrender\.com", origin
    ):
        print("Set TNR_BACKEND_URL to the exact HTTPS onrender.com backend origin.")
        return 1
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", secret):
        print("Set a valid digest trigger secret.")
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
                print(f"Health check refused (HTTP {exc.code}); no digest requested.")
                return 1
        except (URLError, OSError, ValueError):
            pass
        if attempt == 11:
            print("Backend did not become ready within the cold-start retry budget.")
            return 1
        time.sleep(5)

    request = Request(
        origin + "/api/briefs/internal/run",
        data=b"",
        headers={"Authorization": "Bearer " + secret},
        method="POST",
    )
    try:
        result = read_json(opener, request, timeout=60)
    except HTTPError as exc:
        if exc.code in (409, 429):
            print(
                f"Digest deferred (HTTP {exc.code}); another scan or cooldown is active."
            )
            return 0
        print(f"Digest request failed (HTTP {exc.code}).")
        return 1
    except (URLError, OSError, ValueError):
        # A timed-out POST may still be running. Do not blindly submit a second attempt.
        print("Digest completion could not be confirmed; POST was not retried.")
        return 1

    allowed = {
        "cached",
        "edition_attempted",
        "unchanged",
        "empty",
        "insufficient_material",
        "disabled",
        "busy",
        "temporary_limit",
        "daily_limit",
        "monthly_budget",
        "activation_required",
        "input_limit",
        "category_cooldown",
        "model_unavailable",
        "provider_unavailable",
        "uncertain",
        "invalid_output",
        "safety_stop",
    }
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("code"), str)
        or result["code"] not in allowed
        or type(result.get("attempts_remaining")) is not int
        or not 0 <= result["attempts_remaining"] <= 24
    ):
        print("Invalid digest result; completion could not be confirmed.")
        return 1
    print(
        f"Digest: {result['code']}; remaining attempts={result['attempts_remaining']}"
    )
    return int(
        result["code"]
        in {
            "model_unavailable",
            "provider_unavailable",
            "uncertain",
            "invalid_output",
            "safety_stop",
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
