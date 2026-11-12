"""Hourly editions use real temporary migrations and simulated inference only."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import ai_fixtures as fixtures
import httpx
import pytest
from alembic import command
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai_briefs import BriefService, select_digest_material
from app.ai_content import DAILY_MESSAGE
from app.api.dependencies import get_identity
from app.main import create_app
from app.models import LOCAL_OWNER_ID, AIBriefControl, AIBriefJob, AppUser, Article

clock, news, provider, service = fixtures.clock, fixtures.news, fixtures.provider, fixtures.service
inference_calls = fixtures.inference_calls

SECRET = "test-only-digest-credential-00000000000"


@pytest.fixture
def digest(service, database):
    service.settings.ai_digest_enabled = True
    service.settings.ai_daily_attempts = 24
    service.settings.ai_daily_tokens = 96000
    service.settings.ai_digest_trigger_secret = SecretStr(SECRET)
    with Session(database) as session, session.begin():
        articles = session.scalars(select(Article).order_by(Article.id)).all()
        for article, title in zip(
            articles[3:],
            [
                "Satellite communications advance",
                "Robots enter new laboratories",
                "Energy storage research progresses",
            ],
            strict=True,
        ):
            article.title = title
    return service


def change_news(database):
    with Session(database) as session, session.begin():
        article = session.scalars(select(Article).order_by(Article.id)).first()
        article.description += (
            " A newly published update adds independent measurements and practical limitations."
        )


@pytest.mark.anyio
async def test_shared_cache_hourly_slots_and_unchanged_material(digest, provider, clock, database):
    _, calls, _ = provider
    before = digest.read(None, LOCAL_OWNER_ID)
    assert before["code"] == "available" and not calls
    result = await digest.generate(None, None)
    assert result["code"] == "cached" and len(result["briefs"]) == 1
    assert len({a["category_name"] for a in result["briefs"][0]["articles"]}) == 2
    assert len(inference_calls(calls)) == 1
    await digest.generate(None, None)
    assert len(inference_calls(calls)) == 1
    clock[0] += timedelta(hours=1)
    assert (await digest.generate(None, None))["code"] == "unchanged"
    change_news(database)
    assert len((await digest.generate(None, None))["briefs"]) == 2
    assert len(inference_calls(calls)) == 2
    with Session(database) as session:
        control = session.get(AIBriefControl, 1)
        assert (control.attempts, control.reserved_tokens) == (2, 8000)


def test_concurrent_last_slot_and_durable_hour_deduplication(digest, database, clock):
    with Session(database) as session, session.begin():
        control = session.get(AIBriefControl, 1)
        control.quota_day, control.attempts, control.reserved_tokens = clock[0].date(), 23, 92000
    barrier = Barrier(2)

    def acquire(_):
        barrier.wait(timeout=5)
        return digest.reserve(None, None)[0]

    with ThreadPoolExecutor(2) as pool:
        assert sum(job is not None for job in pool.map(acquire, range(2))) == 1
    with Session(database) as session:
        control = session.get(AIBriefControl, 1)
        assert (control.attempts, control.reserved_tokens) == (24, 96000)
        assert len(session.scalars(select(AIBriefJob)).all()) == 1
    assert digest.read(None, LOCAL_OWNER_ID)["code"] == "daily_limit"


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["timeout", 429, 503])
async def test_failed_editions_never_retry_and_keep_reservations(
    digest, provider, clock, database, failure
):
    _, calls, mode = provider
    mode["timeout" if failure == "timeout" else "status"] = (
        True if failure == "timeout" else failure
    )
    await digest.generate(None, None)
    clock[0] += timedelta(minutes=10)
    restarted = BriefService(database, digest.settings, digest.provider)
    await restarted.generate(None, None)
    assert len(inference_calls(calls)) == 1
    with Session(database) as session:
        assert session.get(AIBriefControl, 1).reserved_tokens == 4000
    clock[0] += timedelta(hours=1)
    await restarted.generate(None, None)
    assert len(inference_calls(calls)) == 1  # Failed material is not resubmitted.


def test_restart_recovers_interrupted_work_without_reacquisition(digest, clock, database):
    first, _ = digest.reserve(None, None)
    clock[0] += timedelta(minutes=3)
    restarted = BriefService(database, digest.settings, digest.provider)
    assert restarted.reserve(None, None)[0] is None
    with Session(database) as session:
        assert session.get(AIBriefJob, first).status == "interrupted"
        assert session.get(AIBriefControl, 1).attempts == 1


@pytest.mark.anyio
async def test_reader_and_operator_routes_keep_separate_permissions(digest, database, provider):
    app = create_app(
        digest.settings.model_copy(
            update={"database_url": database.url.render_as_string(hide_password=False)}
        )
    )
    app.dependency_overrides[get_identity] = lambda: LOCAL_OWNER_ID
    async with app.router.lifespan_context(app):
        app.state.briefs = digest
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            for credential in ("", "Bearer user-session-token", "Bearer wrong-secret"):
                result = await client.post(
                    "/api/briefs/internal/run", headers={"Authorization": credential}
                )
                assert result.status_code == 401
            assert (await client.post("/api/briefs/1/generate")).status_code == 404
            for _ in range(3):
                result = await client.get("/api/briefs/digest")
                assert result.status_code == 200 and not result.json()["can_generate"]
            assert not provider[1]
            app.dependency_overrides.clear()
            assert (
                await client.get(
                    "/api/briefs/digest", headers={"Authorization": "Bearer " + SECRET}
                )
            ).status_code == 401
            result = await client.post(
                "/api/briefs/internal/run", headers={"Authorization": "Bearer " + SECRET}
            )
            assert result.status_code == 200 and set(result.json()) == {
                "code",
                "attempts_remaining",
            }
            assert len(inference_calls(provider[1])) == 1
            await client.post(
                "/api/briefs/internal/run", headers={"Authorization": "Bearer " + SECRET}
            )
            assert len(inference_calls(provider[1])) == 1
            with Session(database) as session, session.begin():
                session.get(AppUser, LOCAL_OWNER_ID).active = False
            app.dependency_overrides[get_identity] = lambda: LOCAL_OWNER_ID
            assert (await client.get("/api/briefs/digest")).status_code == 403


@pytest.mark.anyio
@pytest.mark.parametrize("identity", ["anonymous", "unapproved"])
async def test_digest_rejects_unapproved_readers(digest, database, identity):
    app = create_app(
        digest.settings.model_copy(
            update={"database_url": database.url.render_as_string(hide_password=False)}
        )
    )
    if identity == "unapproved":
        app.dependency_overrides[get_identity] = lambda: uuid4()
    async with app.router.lifespan_context(app):
        app.state.briefs = digest
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (await client.get("/api/briefs/digest")).status_code == (
                401 if identity == "anonymous" else 403
            )


def test_database_unique_edition_and_migration_preserves_ledger(
    digest, database, migration_config, clock
):
    job_id, _ = digest.reserve(None, None)
    with Session(database) as session:
        job = session.get(AIBriefJob, job_id)
        values = {column.name: getattr(job, column.name) for column in AIBriefJob.__table__.columns}
    values["id"] = uuid4()
    with pytest.raises(IntegrityError), database.begin() as connection:
        connection.execute(AIBriefJob.__table__.insert().values(**values))
    with pytest.raises(RuntimeError, match="AI usage history"):
        command.downgrade(migration_config, "0007")
    command.upgrade(migration_config, "head")
    command.check(migration_config)
    with Session(database) as session:
        assert session.get(AIBriefControl, 1).attempts == 1
        assert session.get(AIBriefJob, job_id).status == "running"


def test_empty_catalog_avoids_calls(digest, database, provider, clock):
    with Session(database) as session, session.begin():
        for article in session.scalars(select(Article)):
            article.description = "Too short"
    with Session(database) as session:
        assert select_digest_material(session, clock[0]) == []
    assert digest.reserve(None, None)[0] is None
    assert not provider[1]


def test_hour_boundary_prevents_late_dispatch_and_utc_reset_preserves_work(digest, clock, database):
    from app.ai_content import AIUnavailable

    clock[0] = clock[0].replace(hour=23, minute=58)
    job, _ = digest.reserve(None, None)
    clock[0] += timedelta(minutes=2)
    with pytest.raises(AIUnavailable):
        digest.dispatch_material(job, None)
    state = digest.read(None, LOCAL_OWNER_ID)
    assert state["attempts_remaining"] == 24
    with Session(database) as session:
        assert session.get(AIBriefJob, job).status == "interrupted"


@pytest.mark.anyio
async def test_direct_operator_and_reader_calls_share_daily_denial(
    digest, database, clock, provider
):
    with Session(database) as session, session.begin():
        control = session.get(AIBriefControl, 1)
        control.quota_day, control.attempts, control.reserved_tokens = clock[0].date(), 24, 96000
    app = create_app(
        digest.settings.model_copy(
            update={"database_url": database.url.render_as_string(hide_password=False)}
        )
    )
    app.dependency_overrides[get_identity] = lambda: LOCAL_OWNER_ID
    async with app.router.lifespan_context(app):
        app.state.briefs = digest
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            for path in ("/api/briefs/internal/run",):
                result = await client.post(path, headers={"Authorization": "Bearer " + SECRET})
                assert (
                    result.status_code == 429
                    and result.json()["detail"]["message"] == DAILY_MESSAGE
                )
            assert (await client.get("/api/briefs/digest")).json()["code"] == "daily_limit"
    assert not provider[1]


def test_running_edition_is_busy_and_cannot_downgrade_a_full_ledger(
    digest, database, clock, migration_config
):
    digest.reserve(None, None)
    assert digest.read(None, LOCAL_OWNER_ID)["code"] == "busy"
    with Session(database) as session, session.begin():
        control = session.get(AIBriefControl, 1)
        control.attempts, control.reserved_tokens = 24, 96000
    with pytest.raises(RuntimeError, match="AI usage history"):
        command.downgrade(migration_config, "0007")
    with Session(database) as session:
        assert session.get(AIBriefControl, 1).reserved_tokens == 96000
