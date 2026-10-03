import httpx
import pytest

from xuemian_ai.main import create_app


@pytest.mark.parametrize(
    "path",
    [
        "/ai-quality-cases/missing",
        "/admin/ai-quality/missing",
        "/admin/prompt-definitions/missing",
        "/admin/prompt-versions/missing",
    ],
)
async def test_sensitive_failed_responses_are_not_cacheable(path: str) -> None:
    app = create_app()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://isolated"
        ) as client,
    ):
        response = await client.get("/api/v1" + path)
    assert response.status_code >= 400
    assert response.headers["cache-control"] == "no-store"
