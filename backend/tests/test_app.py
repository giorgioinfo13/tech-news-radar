from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import URL, event

from app.config import Settings
from app.main import create_app


@pytest.mark.anyio
async def test_health_contract_and_openapi() -> None:
    settings = Settings(_env_file=None, app_name="Test Radar", docs_enabled=True)
    transport = ASGITransport(app=create_app(settings))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        schema = (await client.get("/openapi.json")).json()
        assert schema["info"]["title"] == "Test Radar"
        assert "/api/health" in schema["paths"]


@pytest.mark.anyio
async def test_environment_can_disable_docs_without_disabling_health(monkeypatch) -> None:
    monkeypatch.setenv("TNR_DOCS_ENABLED", "false")
    transport = ASGITransport(app=create_app(Settings(_env_file=None)))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/docs")).status_code == 404
        assert (await client.get("/openapi.json")).status_code == 404
        assert (await client.get("/api/health")).status_code == 200


@pytest.mark.anyio
async def test_lifespan_and_health_do_not_create_database(tmp_path: Path) -> None:
    database_path = tmp_path / "uninitialized.db"
    settings = Settings(
        _env_file=None,
        database_url=URL.create("sqlite", database=str(database_path)).render_as_string(),
        scheduler_enabled=False,
    )
    app = create_app(settings)
    disposed = []
    async with app.router.lifespan_context(app):
        event.listen(
            app.state.database_engine, "engine_disposed", lambda engine: disposed.append(True)
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/api/health")).status_code == 200
            schema = (await client.get("/openapi.json")).json()
            assert {"get", "post"} <= schema["paths"]["/api/sources"].keys()
            assert "patch" in schema["paths"]["/api/articles/{article_id}"]
        assert not database_path.exists()
    assert disposed == [True]
    assert not database_path.exists()
