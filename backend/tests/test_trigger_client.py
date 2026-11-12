import importlib.util
import json
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

SPEC = importlib.util.spec_from_file_location(
    "trigger_client", Path(__file__).resolve().parents[2] / "scripts/trigger_collection.py"
)
client = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(client)
SECRET = "test-only-collection-secret-000000000000"
OK = {"collected": 1, "failed": 0, "skipped": 2, "deferred": False}


class Reply(BytesIO):
    status = 200

    def __init__(self, body):
        super().__init__(json.dumps(body).encode() if not isinstance(body, bytes) else body)


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.setenv("TNR_BACKEND_URL", "https://example.onrender.com")
    monkeypatch.setenv("TNR_COLLECTION_TRIGGER_SECRET", SECRET)
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


def test_cold_start_does_not_send_secret_until_ready(runner, capsys):
    replies, requests, waits = runner
    replies.extend([URLError("private error"), b"<html>Waking up</html>", {"status": "ok"}, OK])
    assert client.main() == 0
    assert waits == [5, 5]
    assert [req.get_method() for req, _ in requests] == ["GET", "GET", "GET", "POST"]
    assert all(req.get_header("Authorization") is None for req, _ in requests[:-1])
    request, timeout = requests[-1]
    assert timeout == 600
    assert request.full_url == "https://example.onrender.com/api/internal/collect"
    assert request.get_header("Authorization") == "Bearer " + SECRET
    output = capsys.readouterr().out
    assert "collected=1" in output
    assert SECRET not in output


def test_cold_start_has_bounded_retries(runner):
    replies, requests, waits = runner
    replies.extend([URLError("unavailable")] * 12)
    assert client.main() == 1
    assert len(requests) == 12
    assert len(waits) == 11
    assert all(req.get_method() == "GET" for req, _ in requests)


@pytest.mark.parametrize(
    "status,code", [(401, 1), (404, 1), (503, 1), (409, 0), (429, 0), (302, 1)]
)
def test_post_is_never_retried_and_raw_error_is_not_logged(runner, capsys, status, code):
    replies, requests, _ = runner
    replies.extend([{"status": "ok"}, HTTPError("private URL", status, SECRET, {}, None)])
    assert client.main() == code
    assert len(requests) == 2
    output = capsys.readouterr().out
    assert SECRET not in output
    assert "private URL" not in output


def test_timeout_after_post_is_ambiguous_and_not_retried(runner, capsys):
    replies, requests, _ = runner
    replies.extend([{"status": "ok"}, TimeoutError(SECRET)])
    assert client.main() == 1
    assert len(requests) == 2
    assert "POST was not retried" in capsys.readouterr().out


@pytest.mark.parametrize(
    "result",
    [
        None,
        {},
        {**OK, "collected": True},
        {**OK, "failed": 1},
        b"x" * (client.MAX_RESPONSE_BYTES + 1),
        b"not JSON",
    ],
)
def test_invalid_or_failed_collection_fails_workflow(runner, result):
    replies, _, _ = runner
    replies.extend([{"status": "ok"}, result])
    assert client.main() == 1


@pytest.mark.parametrize("collected", [0, 25, 100])
def test_deferred_work_warns_without_failing_or_repeating_post(runner, capsys, collected):
    replies, requests, _ = runner
    replies.extend([{"status": "ok"}, {**OK, "collected": collected, "deferred": True}])
    assert client.main() == 0
    assert "::warning::Collection deferred" in capsys.readouterr().out
    assert [request.get_method() for request, _ in requests] == ["GET", "POST"]


@pytest.mark.parametrize("deferred", [False, True])
def test_failures_remain_errors_with_identifiable_safe_diagnostics(runner, capsys, deferred):
    replies, _, _ = runner
    replies.extend(
        [
            {"status": "ok"},
            {
                **OK,
                "failed": 2,
                "deferred": deferred,
                "failures": [
                    {"source_id": 7, "run_id": 43, "reason": "http_503"},
                    {"source_id": 8, "run_id": None, "reason": "unexpected_error"},
                ],
            },
        ]
    )
    assert client.main() == 1
    output = capsys.readouterr().out
    assert "::error::Collection failed: source_id=7, run_id=43, reason=http_503" in output
    assert "source_id=8, run_id=None, reason=unexpected_error" in output
    assert ("::warning::Collection deferred" in output) is deferred


def test_old_backend_failure_still_fails_and_explains_missing_diagnostics(runner, capsys):
    replies, _, _ = runner
    replies.extend([{"status": "ok"}, {**OK, "failed": 1}])
    assert client.main() == 1
    assert "Source diagnostics unavailable" in capsys.readouterr().out


def test_all_100_failure_diagnostics_fit_bounded_response(runner, capsys):
    replies, _, _ = runner
    failures = [
        {"source_id": 2**63 - 1 - i, "run_id": 2**63 - 1, "reason": "unsafe_destination"}
        for i in range(100)
    ]
    replies.extend([{"status": "ok"}, {**OK, "failed": 100, "failures": failures}])
    assert client.main() == 1
    assert capsys.readouterr().out.count("::error::Collection failed:") == 100


@pytest.mark.parametrize(
    "failure",
    [
        {"source_id": True, "run_id": 1, "reason": "timeout"},
        {"source_id": -1, "run_id": 1, "reason": "timeout"},
        {"source_id": 1, "run_id": False, "reason": "timeout"},
        {"source_id": 1, "run_id": 0, "reason": "timeout"},
        {"source_id": 1, "run_id": 1, "reason": "private credential\n::error::injected"},
        {"source_id": 1, "run_id": 1, "reason": []},
        "private credential",
    ],
)
def test_invalid_diagnostics_do_not_leak_or_inject_workflow_commands(runner, capsys, failure):
    replies, _, _ = runner
    replies.extend([{"status": "ok"}, {**OK, "failed": 1, "failures": [failure]}])
    assert client.main() == 1
    output = capsys.readouterr().out
    assert "Invalid failure diagnostics" in output
    assert "private credential" not in output
    assert "::error::" not in output


@pytest.mark.parametrize(
    "origin",
    [
        "http://example.onrender.com",
        "https://example.onrender.com.evil.test",
        "https://secret@example.onrender.com",
        "https://example.onrender.com/path",
        "https://example.onrender.com?secret=123",
        "https://127.0.0.1",
        "",
    ],
)
def test_invalid_destinations_do_not_receive_credentials(runner, monkeypatch, origin):
    _, requests, _ = runner
    monkeypatch.setenv("TNR_BACKEND_URL", origin)
    assert client.main() == 1
    assert requests == []


def test_missing_secret_prevents_even_wake_request(runner, monkeypatch):
    _, requests, _ = runner
    monkeypatch.delenv("TNR_COLLECTION_TRIGGER_SECRET")
    assert client.main() == 1
    assert requests == []


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirects_cannot_forward_secret(status):
    handler = client.NoRedirects()
    request = client.Request("https://example.onrender.com", headers={"Authorization": SECRET})
    assert (
        handler.redirect_request(request, None, status, "redirect", {}, "https://evil.test") is None
    )


def test_wrong_health_origin_is_not_followed(runner):
    replies, requests, _ = runner
    replies.append(HTTPError("private URL", 302, "redirect", {}, None))
    assert client.main() == 1
    assert len(requests) == 1
