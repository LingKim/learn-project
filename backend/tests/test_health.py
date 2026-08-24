from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from xuemian_ai.api import health as health_module
from xuemian_ai.api.health import DependencyCheck, ReadyResponse
from xuemian_ai.main import app


async def test_live_reports_process_status() -> None:
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get(
                "/api/v1/health/live",
                headers={"x-request-id": "test-request"},
            )

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "xuemian-ai-backend"}
    assert response.headers["x-request-id"] == "test-request"


async def test_ready_returns_503_when_a_dependency_is_down(monkeypatch: MonkeyPatch) -> None:
    result = ReadyResponse(
        status="degraded",
        checks={
            "postgresql": DependencyCheck(status="up", code="ok"),
            "redis": DependencyCheck(status="down", code="redis_unavailable"),
            "rustfs": DependencyCheck(status="up", code="ok"),
        },
    )
    probe = AsyncMock(return_value=result)
    monkeypatch.setattr(health_module, "run_readiness_checks", probe)

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["checks"]["redis"]["code"] == "redis_unavailable"


def test_ai_dependencies_are_importable() -> None:
    import langchain
    import langgraph

    assert langchain is not None
    assert langgraph is not None
