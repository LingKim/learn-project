from fastapi.testclient import TestClient

from xuemian_ai.main import create_app


def test_swagger_uses_proxy_safe_relative_openapi_url() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/docs")

    assert response.status_code == 200
    assert "url: './openapi.json'" in response.text


def test_redoc_uses_proxy_safe_relative_openapi_url() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/redoc")

    assert response.status_code == 200
    assert 'spec-url="./openapi.json"' in response.text
