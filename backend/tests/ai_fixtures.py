"""Shared simulated Gemini responses and isolated RSS fixtures. No live HTTP."""

import json
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.orm import Session

from app import ai_gemini
from app.ai_briefs import BriefService
from app.ai_gemini import MODEL, Gemini
from app.config import Settings
from app.models import Article, Source

SECRET = "simulation-only-operator-credential-0000"

SUMMARY = " ".join(
    ["Le notizie raccolte descrivono sviluppi tecnologici riportati dalle fonti disponibili."] * 13
)
DESCRIPTION = (
    "La fonte presenta una nuova versione del progetto e descrive le modifiche introdotte, "
    "le prove pubblicate e i limiti ancora presenti. I dettagli provengono dalla descrizione RSS."
)


@pytest.fixture
def clock(monkeypatch):
    value = [datetime(2026, 11, 9, 12, tzinfo=UTC)]
    monkeypatch.setattr("app.ai_briefs.database_now", lambda session: value[0])
    return value


@pytest.fixture
def news(database, clock):
    with Session(database) as session, session.begin():
        for category_id in (1, 2):
            source = Source(
                name="Public news",
                feed_url=f"https://news{category_id}.example/feed",
                category_id=category_id,
            )
            session.add(source)
            session.flush()
            for i, title in enumerate(
                (
                    "Compiler performance improves",
                    "Database release adds a storage option",
                    "Researchers compare evaluation methods",
                )
            ):
                session.add(
                    Article(
                        source_id=source.id,
                        title=title,
                        description=DESCRIPTION,
                        url=f"https://news{category_id}.example/{i}",
                        published_at=clock[0],
                    )
                )


def response_for(body):
    articles = json.loads(body["contents"][0]["parts"][0]["text"])
    return {
        "modelVersion": MODEL,
        "usageMetadata": {
            "promptTokenCount": 800,
            "candidatesTokenCount": 300,
            "thoughtsTokenCount": 100,
            "totalTokenCount": 1200,
        },
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "summary": SUMMARY,
                                    "article_ids": [a["id"] for a in articles],
                                }
                            )
                        }
                    ]
                },
            }
        ],
    }


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(ai_gemini, "LIVE_CONTRACT_VERIFIED", True)
    calls, mode = [], {}

    async def handle(request):
        calls.append(request)
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.url.query == b""
        assert request.headers["x-goog-api-key"] == "simulation-only-key"
        body = json.loads(request.content)
        if request.url.path.endswith(":countTokens"):
            if callback := mode.get("after_count"):
                callback()
            if mode.get("count_error"):
                raise httpx.ReadTimeout("simulation-only-key")
            return httpx.Response(200, json={"totalTokens": mode.get("count", 800)})
        assert request.url.path == f"/v1beta/models/{MODEL}:generateContent"
        if mode.get("timeout"):
            raise httpx.ReadTimeout("simulation-only-key")
        data = response_for(body)
        if mode.get("mutate"):
            mode["mutate"](data)
        return httpx.Response(mode.get("status", 200), json=data, headers=mode.get("headers", {}))

    settings = Settings(
        _env_file=None,
        ai_briefs_enabled=True,
        ai_digest_enabled=True,
        ai_privacy_reviewed=True,
        gemini_api_key="simulation-only-key",
        ai_digest_trigger_secret=SECRET,
        scheduler_enabled=False,
    )
    adapter = Gemini(settings, httpx.MockTransport(handle))
    return adapter, calls, mode


@pytest.fixture
def service(database, news, provider):
    adapter, _, _ = provider
    return BriefService(database, adapter.settings, adapter)


@pytest.fixture
def gemini(service, provider):
    return service, provider[1], provider[2]


def inference_calls(calls):
    return [request for request in calls if request.url.path.endswith(":generateContent")]
