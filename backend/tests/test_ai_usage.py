"""Gemini statistics use local PostgreSQL and simulated HTTP only."""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import ai_fixtures as fixtures
import pytest
from alembic import command
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session
from test_multiuser import people as people_fixture

from app.ai_gemini import RESERVATION_NANO_USD
from app.models import LOCAL_OWNER_ID, AIBriefBudget, AIBriefJob, AIBriefUsage, AppUser

clock, news, provider, service, gemini = (
    fixtures.clock,
    fixtures.news,
    fixtures.provider,
    fixtures.service,
    fixtures.gemini,
)
people = people_fixture
PATH = "/api/usage/gemini?month=2026-11-01"


@pytest.mark.anyio
async def test_usage_persists_success_and_reads_do_not_generate_or_count_again(
    gemini, people, database
):
    service, calls, _ = gemini
    clients = people[0]
    await service.generate(None, None)
    for _ in range(2):
        await service.generate(None, None)
        response = await clients["admin"].get(PATH)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "private, no-store"
        data = response.json()
        assert data["summary"] == {
            "attempts": 1,
            "successes": 1,
            "measured_attempts": 1,
            "unverified_attempts": 0,
            "unavailable_attempts": 0,
            "input_tokens": 800,
            "output_tokens": 300,
            "thought_tokens": 100,
            "total_tokens": 1200,
            "estimated_nano_usd": 800_000,
            "reserved_nano_usd": RESERVATION_NANO_USD,
        }
        attempt = data["attempts"]["items"][0]
        assert attempt["counted_tokens"] == 800
        assert attempt["usage_state"] == "measured"
        assert attempt["status"] == "success"
        assert data["days"][0]["day"] == "2026-11-09"
        assert data["budget_reserved_nano_usd"] == RESERVATION_NANO_USD
        assert not {"summary", "articles", "diagnostics", "user_id"} & attempt.keys()
        assert "simulation-only-key" not in response.text
    assert len(calls) == 2
    with Session(database) as session:
        assert len(session.scalars(select(AIBriefUsage)).all()) == 1
    assert (await clients["alice"].get(PATH)).status_code == 403
    assert (await clients["bob"].get(PATH)).status_code == 403
    with Session(database) as session, session.begin():
        session.get(AppUser, LOCAL_OWNER_ID).active = False
    assert (await clients["admin"].get(PATH)).status_code == 403


@pytest.mark.anyio
@pytest.mark.parametrize(
    "outcome", ["invalid_json", "shape", "timeout", "count_timeout", "mismatch", "http_error"]
)
async def test_failed_attempts_keep_known_usage_and_distinguish_unknown(gemini, people, outcome):
    service, calls, mode = gemini
    if outcome == "invalid_json":
        mode["mutate"] = lambda data: data["candidates"][0]["content"]["parts"][0].update(
            text="bad"
        )
    elif outcome == "shape":
        mode["mutate"] = lambda data: data.update(candidates=[])
    elif outcome == "timeout":
        mode["timeout"] = True
    elif outcome == "count_timeout":
        mode["count_error"] = True
    elif outcome == "http_error":
        mode["status"] = 500  # Metadata can accompany a failed response.
    else:
        mode["mutate"] = lambda data: data["usageMetadata"].update(totalTokenCount=9999)
    await service.generate(None, None)
    response = await people[0]["admin"].get(PATH)
    assert response.status_code == 200
    data = response.json()
    attempt = data["attempts"]["items"][0]
    assert attempt["status"] == "error"
    known = outcome in {"invalid_json", "shape", "http_error"}
    assert attempt["usage_state"] == (
        "measured" if known else "unverified" if outcome == "mismatch" else "unavailable"
    )
    assert data["summary"]["estimated_nano_usd"] == (800_000 if known else None)
    assert data["summary"]["total_tokens"] == (1200 if known else None)
    assert attempt["counted_tokens"] == (None if outcome == "count_timeout" else 800)
    if outcome == "mismatch":
        assert attempt["total_tokens"] == 9999
    assert len(calls) == (1 if outcome == "count_timeout" else 2)


@pytest.mark.anyio
async def test_month_boundaries_pagination_expiry_and_retention(gemini, people, database, clock):
    service, calls, _ = gemini
    await service.generate(None, None)
    # Two durable records on either side of UTC month end. No content is needed.
    with Session(database) as session, session.begin():
        for when in (datetime(2026, 10, 31, 23, 59, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)):
            session.add(
                AIBriefUsage(
                    id=uuid4(),
                    started_at=when,
                    edition_at=when,
                    lease_until=when + timedelta(minutes=2),
                    model="legacy-model",
                    status="running",
                    reserved_nano_usd=100,
                )
            )
    clock[0] += timedelta(days=8)
    service.read(None, LOCAL_OWNER_ID)
    with Session(database) as session:
        assert session.scalars(select(AIBriefJob)).first() is None
    client = people[0]["admin"]
    first = (await client.get(PATH + "&limit=1")).json()
    assert first["summary"]["attempts"] == first["attempts"]["total"] == 2
    assert first["summary"]["total_tokens"] == 1200
    assert first["summary"]["unavailable_attempts"] == 1
    second = (await client.get(PATH + "&limit=1&offset=1")).json()
    assert second["summary"] == first["summary"]
    assert second["attempts"]["items"][0]["status"] == "interrupted"
    assert second["attempts"]["items"][0]["usage_state"] == "unavailable"
    assert first["attempts"]["items"][0]["id"] != second["attempts"]["items"][0]["id"]
    october = (await client.get("/api/usage/gemini?month=2026-10-01")).json()
    assert october["attempts"]["total"] == 1
    assert october["summary"]["total_tokens"] is None
    assert len(calls) == 2


@pytest.mark.anyio
async def test_empty_month_keeps_historical_budget_and_rejects_bad_filters(people, database):
    with Session(database) as session, session.begin():
        session.add(AIBriefBudget(month=date(2026, 11, 1), reserved_nano_usd=12_000_000))
    client = people[0]["admin"]
    data = (await client.get(PATH)).json()
    assert data["summary"]["attempts"] == 0
    assert data["summary"]["total_tokens"] == 0
    assert data["budget_reserved_nano_usd"] == 12_000_000
    assert data["days"] == []
    for query in ("month=2026-11-12", "month=no", "month=9999-12-01", "limit=0", "offset=-1"):
        assert (await client.get("/api/usage/gemini?" + query)).status_code == 422


def test_migration_backfills_safe_numbers_without_inventing_success_usage(
    database, migration_config
):
    command.downgrade(migration_config, "0012")
    when = datetime(2026, 11, 10, tzinfo=UTC)
    with Session(database) as session, session.begin():
        for index, diagnostics in enumerate(
            (
                None,
                {
                    "input_tokens": 800,
                    "output_tokens": True,
                    "counted_tokens": "SECRET",
                    "total_tokens": 999999999999999999,
                },
            )
        ):
            session.add(
                AIBriefJob(
                    id=uuid4(),
                    category_name="Old",
                    started_at=when + timedelta(hours=index),
                    quota_day=when.date(),
                    window_start=when - timedelta(days=1),
                    window_end=when,
                    lease_until=when + timedelta(minutes=2),
                    finished_at=when,
                    status="success",
                    articles=[],
                    summary="private old text",
                    model="old-model",
                    diagnostics=diagnostics,
                )
            )
    command.upgrade(migration_config, "head")
    command.check(migration_config)
    with Session(database) as session:
        rows = session.scalars(select(AIBriefUsage).order_by(AIBriefUsage.started_at)).all()
        assert len(rows) == 2
        assert rows[0].input_tokens is None and rows[1].input_tokens == 800
        assert rows[1].output_tokens is None and rows[1].total_tokens is None
        assert rows[1].counted_tokens is None
        assert all(not row.usage_validated and row.estimated_nano_usd is None for row in rows)
    with pytest.raises(RuntimeError, match="Cannot discard AI usage history"):
        command.downgrade(migration_config, "0012")
    with database.connect() as connection:
        for role in ("anon", "authenticated", "service_role"):
            assert not connection.scalar(
                text(
                    "SELECT has_table_privilege(:role, 'tnr.ai_brief_usage', "
                    "'SELECT,INSERT,UPDATE,DELETE')"
                ),
                {"role": role},
            )
    with Session(database) as session, session.begin():
        session.execute(delete(AIBriefUsage))
        session.execute(delete(AIBriefJob))
    command.downgrade(migration_config, "0012")
    command.upgrade(migration_config, "head")


@pytest.mark.anyio
async def test_late_response_accounts_tokens_without_saving_an_expired_digest(
    gemini, people, database, clock
):
    from app.ai_gemini import validate_usage

    service, calls, _ = gemini
    job_id, _ = service.reserve(None, None)
    material = service.dispatch_material(job_id, None, claim=True, counted=800)
    clock[0] += timedelta(minutes=3)
    metrics = validate_usage(
        {
            "modelVersion": service.provider.model,
            "usageMetadata": {
                "promptTokenCount": 800,
                "candidatesTokenCount": 300,
                "totalTokenCount": 1100,
            },
        },
        800,
    )
    service.finish(
        job_id, {"summary": fixtures.SUMMARY, "articles": material, "usage": metrics}, None
    )
    data = (await people[0]["admin"].get(PATH)).json()
    assert data["summary"]["successes"] == 0
    assert data["summary"]["total_tokens"] == 1100
    assert data["attempts"]["items"][0]["status"] == "interrupted"
    assert data["attempts"]["items"][0]["thought_tokens"] == 0
    service.read(None, LOCAL_OWNER_ID)
    with Session(database) as session:
        assert session.get(AIBriefJob, job_id).status == "interrupted"
        assert session.get(AIBriefUsage, job_id).total_tokens == 1100
    assert not calls
