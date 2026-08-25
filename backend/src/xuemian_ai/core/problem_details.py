from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from xuemian_ai.core.errors import AppError
from xuemian_ai.core.logging import get_logger, safe_exception_fields
from xuemian_ai.core.request_context import route_template
from xuemian_ai.core.responses import ApiResponse, PageResponse
from xuemian_ai.core.status_codes import ApiStatusCode

_logger = get_logger(__name__)


class ValidationIssue(BaseModel):
    field: str
    message: str


class ProblemDetails(BaseModel):
    type: str
    title: str
    status: int
    detail: str
    instance: str
    code: int
    message: str
    data: None
    error_key: str | None = None
    request_id: str | None = None
    errors: list[ValidationIssue] | None = None


PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.value: {
        "model": ProblemDetails,
        "description": description,
    }
    for status, description in (
        (ApiStatusCode.BAD_REQUEST, "请求参数错误"),
        (ApiStatusCode.UNAUTHORIZED, "身份认证失败"),
        (ApiStatusCode.FORBIDDEN, "没有访问权限"),
        (ApiStatusCode.NOT_FOUND, "资源不存在"),
        (ApiStatusCode.METHOD_NOT_ALLOWED, "请求方法不支持"),
        (ApiStatusCode.CONFLICT, "资源状态冲突"),
        (ApiStatusCode.VALIDATION_ERROR, "请求参数校验失败"),
        (ApiStatusCode.TOO_MANY_REQUESTS, "请求过于频繁"),
        (ApiStatusCode.INTERNAL_SERVER_ERROR, "服务内部错误"),
        (ApiStatusCode.BAD_GATEWAY, "上游服务异常"),
        (ApiStatusCode.SERVICE_UNAVAILABLE, "服务暂时不可用"),
        (ApiStatusCode.GATEWAY_TIMEOUT, "上游服务超时"),
    )
}

_DEFAULT_HTTP_MESSAGES = {
    ApiStatusCode.NOT_FOUND.value: "请求的资源不存在",
    ApiStatusCode.METHOD_NOT_ALLOWED.value: "请求方法不支持",
}

_DEFAULT_HTTP_TITLES = {
    ApiStatusCode.NOT_FOUND.value: "资源不存在",
    ApiStatusCode.METHOD_NOT_ALLOWED.value: "请求方法不支持",
}

_DEFAULT_HTTP_ERROR_KEYS = {
    ApiStatusCode.NOT_FOUND.value: "RESOURCE_NOT_FOUND",
    ApiStatusCode.METHOD_NOT_ALLOWED.value: "METHOD_NOT_ALLOWED",
}


def _problem(
    request: Request,
    *,
    status: int,
    title: str,
    message: str,
    error_type: str = "about:blank",
    error_key: str | None = None,
    headers: Mapping[str, str] | None = None,
    errors: list[ValidationIssue] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    body = ProblemDetails(
        type=error_type,
        title=title,
        status=status,
        detail=message,
        instance=request.url.path,
        code=status,
        message=message,
        data=None,
        error_key=error_key,
        request_id=request_id,
        errors=errors,
    )
    content = body.model_dump(mode="json", exclude_none=True)
    content["data"] = None
    response_headers = dict(headers) if headers is not None else {}
    if request_id is not None:
        response_headers.setdefault("x-request-id", request_id)
    return JSONResponse(
        content,
        status_code=status,
        headers=response_headers,
        media_type="application/problem+json",
    )


def _validation_issues(exc: RequestValidationError) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    request_sources = {"body", "query", "path", "header", "cookie"}
    for error in exc.errors():
        location = list(error.get("loc", ()))
        if location and location[0] in request_sources:
            location = location[1:]
        field = ".".join(str(part) for part in location) or "$"
        issues.append(ValidationIssue(field=field, message=str(error.get("msg", "输入不合法"))))
    return issues


def register_problem_handlers(app: FastAPI) -> None:
    original_openapi = app.openapi

    def openapi_with_problem_media_type() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = original_openapi()
        component_schemas = schema.setdefault("components", {}).setdefault("schemas", {})
        for name, model_schema in (
            (
                "ApiResponse",
                ApiResponse[Any].model_json_schema(ref_template="#/components/schemas/{model}"),
            ),
            (
                "PageResponse",
                PageResponse[Any].model_json_schema(ref_template="#/components/schemas/{model}"),
            ),
        ):
            definitions = model_schema.pop("$defs", {})
            component_schemas.update(definitions)
            component_schemas.setdefault(name, model_schema)
        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                if not isinstance(operation, dict):
                    continue
                for response in operation.get("responses", {}).values():
                    content = response.get("content", {})
                    json_media = content.get("application/json")
                    if not isinstance(json_media, dict):
                        continue
                    response_schema = json_media.get("schema", {})
                    if response_schema.get("$ref", "").endswith("/ProblemDetails"):
                        content["application/problem+json"] = content.pop("application/json")
        app.openapi_schema = schema
        return schema

    app.openapi = openapi_with_problem_media_type  # type: ignore[method-assign]

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return _problem(
            request,
            status=exc.status_code.value,
            title=exc.title,
            message=exc.message,
            error_type=exc.error_type,
            error_key=exc.error_key,
            headers=exc.headers,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = _DEFAULT_HTTP_MESSAGES.get(exc.status_code, str(exc.detail))
        return _problem(
            request,
            status=exc.status_code,
            title=_DEFAULT_HTTP_TITLES.get(exc.status_code, "请求失败"),
            message=message,
            error_key=_DEFAULT_HTTP_ERROR_KEYS.get(exc.status_code),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = _validation_issues(exc)
        return _problem(
            request,
            status=ApiStatusCode.VALIDATION_ERROR.value,
            title="请求参数不合法",
            message=f"请求包含 {len(errors)} 个参数错误。",
            error_type="https://xuemian.ai/problems/validation-error",
            error_key="VALIDATION_ERROR",
            errors=errors,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        _logger.error(
            "unhandled_exception",
            route=route_template(request),
            request_id=getattr(request.state, "request_id", None),
            **safe_exception_fields(exc),
        )
        return _problem(
            request,
            status=ApiStatusCode.INTERNAL_SERVER_ERROR.value,
            title="服务内部错误",
            message="服务暂时无法完成请求，请稍后重试。",
            error_type="https://xuemian.ai/problems/internal-server-error",
            error_key="INTERNAL_SERVER_ERROR",
        )
