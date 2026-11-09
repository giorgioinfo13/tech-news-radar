import importlib.util
import json
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

SPEC = importlib.util.spec_from_file_location(
    "digest_trigger_client", Path(__file__).resolve().parents[2] / "scripts/trigger_digest.py"
)
client = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(client)
SECRET = "test-only-collection-secret-000000000000"
OK = {"code": "cached", "attempts_remaining": 23}


class Reply(BytesIO):
    status = 200

    def __init__(self, body):
        super().__init__(json.dumps(body).encode() if not isinstance(body, bytes) else body)


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.setenv("TNR_BACKEND_URL", "https://example.onrender.com")
    monkeypatch.setenv("TNR_AI_DIGEST_TRIGGER_SECRET", SECRET)
    replies, requests, waits = [], [], []

    class Opener:
        def open(self, request, timeout):
            requests.append((request, timeout))
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return Reply(reply)

    monkeypatch.setattr(client, "build_opener", lambda handler: Opener())
    monkeypatch.setattr(client.time, "sleep", waits.append)
    return replies, requests, waits


def test_cold_start_gets_are_safe_and_only_one_post_runs(runner, capsys):
    replies, requests, waits = runner
    replies.extend([URLError(SECRET), {"status": "ok"}, OK])
    assert client.main() == 0
    assert waits == [5]
    assert [request.get_method() for request, _ in requests] == ["GET", "GET", "POST"]
    assert all(request.get_header("Authorization") is None for request, _ in requests[:-1])
    assert requests[-1][0].full_url.endswith("/api/briefs/internal/run")
    assert requests[-1][0].get_header("Authorization") == "Bearer " + SECRET
    assert SECRET not in capsys.readouterr().out


@pytest.mark.parametrize(
    "failure",
    [
        TimeoutError(SECRET),
        HTTPError("private", 429, SECRET, {}, None),
        HTTPError("private", 503, SECRET, {}, None),
    ],
)
def test_uncertain_or_denied_post_is_never_retried(runner, failure, capsys):
    replies, requests, _ = runner
    replies.extend([{"status": "ok"}, failure])
    client.main()
    assert len(requests) == 2
    assert SECRET not in capsys.readouterr().out


@pytest.mark.parametrize(
    "reply",
    [
        {},
        {"code": SECRET, "attempts_remaining": 1},
        {"code": "cached", "attempts_remaining": True},
        {"code": "cached", "attempts_remaining": 25},
        b"not-json",
    ],
)
def test_malformed_result_never_leaks_or_retries(runner, reply, capsys):
    replies, requests, _ = runner
    replies.extend([{"status": "ok"}, reply])
    assert client.main() == 1 and len(requests) == 2
    assert SECRET not in capsys.readouterr().out


def test_redirect_never_forwards_trigger_secret():
    assert (
        client.NoRedirects().redirect_request(None, None, 302, "", {}, "https://attacker.example")
        is None
    )
