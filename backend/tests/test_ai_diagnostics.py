"""Safe diagnostics for simulated Gemini responses; never retain external text."""

import json
from datetime import UTC, datetime

import httpx
import pytest
from ai_fixtures import response_for

from app.ai_content import AIUnavailable
from app.ai_diagnostics import provider_diagnostics, retry_after
from app.ai_gemini import Gemini, payload_for, validate_output
from app.config import Settings

NOW = datetime(2026, 11, 9, 12, tzinfo=UTC)
ARTICLES = [{"id": i, "title": "News", "description": "Public RSS"} for i in (1, 2)]


@pytest.mark.parametrize(
    "issue",
    [
        "response_shape",
        "incomplete_response",
        "invalid_json",
        "invalid_schema",
        "duplicate_citations",
        "unknown_citations",
        "summary_word_count",
        "unsafe_summary",
    ],
)
def test_output_rejection_identifies_rule_without_retaining_provider_text(issue):
    output = {"summary": "news " * 120, "article_ids": [1, 2]}
    if issue == "invalid_schema":
        output["private-provider-field"] = "private-provider-text"
    elif issue == "duplicate_citations":
        output["article_ids"] = [1, 1]
    elif issue == "unknown_citations":
        output["article_ids"] = [1, 999]
    elif issue == "summary_word_count":
        output["summary"] = "news " * 20
    elif issue == "unsafe_summary":
        output["summary"] += "<private-provider-text>"
    data = response_for(payload_for(ARTICLES))
    candidate = data["candidates"][0]
    candidate["content"]["parts"][0]["text"] = (
        "private-provider-text" if issue == "invalid_json" else json.dumps(output)
    )
    if issue == "incomplete_response":
        candidate["finishReason"] = "MAX_TOKENS"
    if issue == "response_shape":
        candidate["content"]["parts"] = []
    with pytest.raises(AIUnavailable) as caught:
        validate_output(data, ARTICLES, 800)
    assert caught.value.code == "invalid_output"
    assert caught.value.diagnostics["output_issue"] == issue
    if issue == "summary_word_count":
        assert caught.value.diagnostics["summary_words"] == 20
    assert "private-provider" not in json.dumps(caught.value.diagnostics)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, (None, "absent")),
        ("0", (0, "seconds")),
        (" 120 ", (120, "seconds")),
        ("90000", (90000, "seconds")),
        ("Mon, 09 Nov 2026 12:02:00 GMT", (120, "http_date")),
        ("Mon, 09 Nov 2026 11:00:00 GMT", (0, "http_date")),
        ("private-error-value", (None, "unparsed")),
        ("-1", (None, "unparsed")),
        ("1.5", (None, "unparsed")),
        ("９０", (None, "unparsed")),
        ("9" * 200, (None, "unparsed")),
    ],
)
def test_retry_after_reports_only_valid_numeric_delays(header, expected):
    assert retry_after(header, NOW) == expected


def test_diagnostics_accept_only_status_and_retry_header():
    assert provider_diagnostics(429, "120", now=NOW) == {
        "http_status": 429,
        "retry_after_kind": "seconds",
        "retry_after_seconds": 120,
    }
    assert provider_diagnostics(503, "private-error-value", now=NOW) == {
        "http_status": 503,
        "retry_after_kind": "unparsed",
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status,retry_header,code,delay",
    [
        (429, "120", "temporary_limit", 120),
        (429, "90000", "temporary_limit", 90000),
        (429, None, "temporary_limit", 3600),
        (429, "private-error-value", "temporary_limit", 3600),
        (401, None, "provider_unavailable", 3600),
        (503, None, "provider_unavailable", 3600),
    ],
)
async def test_adapter_keeps_sanitized_diagnostics_without_retry(
    status, retry_header, code, delay, caplog, capsys, monkeypatch
):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            headers={"Retry-After": retry_header} if retry_header else {},
            json={
                "error": {
                    "code": status,
                    "message": "private-error-value",
                    "details": [{"metadata": {"key": "private-error-value"}}],
                }
            },
        )

    adapter = Gemini(
        Settings(
            _env_file=None,
            ai_briefs_enabled=True,
            ai_digest_enabled=True,
            ai_privacy_reviewed=True,
            ai_budget_risk_accepted=True,
            gemini_api_key="private-error-value",
            scheduler_enabled=False,
        ),
        httpx.MockTransport(handler),
    )
    with pytest.raises(AIUnavailable) as caught:
        await adapter._request("generateContent", payload_for(ARTICLES), counted=800)
    error = caught.value
    assert error.code == code and error.delay == delay
    assert error.diagnostics["http_status"] == status
    assert len(calls) == 1
    assert "private-error-value" not in json.dumps(error.diagnostics)
    assert (
        "private-error-value"
        not in repr(error) + str(error) + caplog.text + capsys.readouterr().out
    )
