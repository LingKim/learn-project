from typing import Annotated

from fastapi import FastAPI, Header
from httpx import ASGITransport, AsyncClient

from xuemian_ai.core.errors import NotFoundError, UnauthorizedError
from xuemian_ai.core.problem_details import PROBLEM_RESPONSES, register_problem_handlers
from xuemian_ai.core.request_context import request_context_middleware
from xuemian_ai.core.responses import ApiResponse, success_response


def create_test_app() -> FastAPI:
    app = FastAPI(responses=PROBLEM_RESPONSES)
    app.middleware("http")(request_context_middleware)
    register_problem_handlers(app)

    @app.get("/success", response_model=ApiResponse[dict[str, str]])
    async def success() -> ApiResponse[dict[str, str]]:
        return success_response({"result": "ok"})

    @app.get("/missing")
    async def missing() -> None:
        raise NotFoundError("面试记录不存在", error_key="INTERVIEW_NOT_FOUND")

    @app.get("/protected")
    async def protected() -> None:
        raise UnauthorizedError(headers={"WWW-Authenticate": "Bearer"})

    @app.get("/validated")
    async def validated(email: Annotated[str, Header(min_length=5)]) -> dict[str, str]:
        return {"email": email}

    @app.get("/crash")
    async def crash() -> None:
        raise RuntimeError("database password must not leak")

    return app


async def test_success_response_has_uniform_shape() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_test_app()), base_url="http://testserver"
    ) as client:
        response = await client.get("/success")

    assert response.status_code == 200
    assert response.json() == {
        "code": 200,
        "message": "请求成功",
        "data": {"result": "ok"},
    }


async def test_app_error_returns_problem_details() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_test_app()), base_url="http://testserver"
    ) as client:
        response = await client.get("/missing", headers={"x-request-id": "missing-request"})

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "https://xuemian.ai/problems/resource-not-found",
        "title": "资源不存在",
        "status": 404,
        "detail": "面试记录不存在",
        "instance": "/missing",
        "code": 404,
        "message": "面试记录不存在",
        "data": None,
        "error_key": "INTERVIEW_NOT_FOUND",
        "request_id": "missing-request",
    }


async def test_authentication_header_is_preserved() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_test_app()), base_url="http://testserver"
    ) as client:
        response = await client.get("/protected")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_starlette_404_and_405_use_problem_details() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_test_app()), base_url="http://testserver"
    ) as client:
        not_found = await client.get("/does-not-exist")
        method_not_allowed = await client.post("/success")

    assert not_found.status_code == 404
    assert not_found.json()["code"] == 404
    assert not_found.json()["error_key"] == "RESOURCE_NOT_FOUND"
    assert method_not_allowed.status_code == 405
    assert method_not_allowed.json()["code"] == 405
    assert method_not_allowed.headers["allow"] == "GET"


async def test_validation_error_exposes_safe_field_issues() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_test_app()), base_url="http://testserver"
    ) as client:
        response = await client.get("/validated", headers={"email": "x"})

    body = response.json()
    assert response.status_code == 422
    assert body["code"] == 422
    assert body["error_key"] == "VALIDATION_ERROR"
    assert body["errors"] == [
        {
            "field": "email",
            "message": "String should have at least 5 characters",
        }
    ]
    assert "input" not in body
    assert "ctx" not in body


async def test_unexpected_error_is_redacted() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_test_app(), raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/crash", headers={"x-request-id": "crash-request"})

    body = response.json()
    assert response.status_code == 500
    assert body["code"] == 500
    assert body["error_key"] == "INTERNAL_SERVER_ERROR"
    assert body["request_id"] == "crash-request"
    assert "password" not in response.text


def test_openapi_contains_success_and_problem_models() -> None:
    schema = create_test_app().openapi()
    success_schema = schema["paths"]["/success"]["get"]["responses"]["200"]
    error_schema = schema["paths"]["/success"]["get"]["responses"]["404"]

    assert success_schema["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ApiResponse_dict_str__str__"
    )
    assert error_schema["content"]["application/problem+json"]["schema"]["$ref"].endswith(
        "/ProblemDetails"
    )
    assert "ApiResponse" in schema["components"]["schemas"]
    assert "PageResponse" in schema["components"]["schemas"]
    assert "PageMeta" in schema["components"]["schemas"]
    assert (
        schema["components"]["schemas"]["PageResponse"]["properties"]["meta"]["$ref"]
        == "#/components/schemas/PageMeta"
    )
