import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


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
