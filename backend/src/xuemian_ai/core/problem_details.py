from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from xuemian_ai.core.errors import AppError
from xuemian_ai.core.logging import get_logger


def _problem(
    request: Request,
    *,
    status: int,
    title: str,
    detail: str,
    error_type: str = "about:blank",
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    body: dict[str, Any] = {
        "type": error_type,
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
    }
    if request_id:
        body["request_id"] = request_id
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


def register_problem_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return _problem(
            request,
            status=exc.status_code,
            title=exc.title,
            detail=exc.detail,
            error_type=exc.error_type,
        )

    @app.exception_handler(HTTPException)
    async def handle_http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return _problem(
            request,
            status=exc.status_code,
            title="请求失败",
            detail=str(exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _problem(
            request,
            status=422,
            title="请求参数不合法",
            detail=f"请求包含 {len(exc.errors())} 个参数错误。",
            error_type="https://xuemian.ai/problems/validation-error",
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        get_logger().exception(
            "unhandled_exception",
            exception_type=type(exc).__name__,
            path=request.url.path,
        )
        return _problem(
            request,
            status=500,
            title="服务内部错误",
            detail="服务暂时无法完成请求，请稍后重试。",
        )
