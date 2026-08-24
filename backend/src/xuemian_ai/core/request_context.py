from collections.abc import Awaitable, Callable
from time import perf_counter
from uuid import uuid4

import structlog.contextvars
from fastapi import Request, Response

from xuemian_ai.core.logging import get_logger

CallNext = Callable[[Request], Awaitable[Response]]


async def request_context_middleware(request: Request, call_next: CallNext) -> Response:
    structlog.contextvars.clear_contextvars()
    request_id = request.headers.get("x-request-id") or str(uuid4())
    request.state.request_id = request_id
    structlog.contextvars.bind_contextvars(request_id=request_id)

    started_at = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        get_logger().exception(
            "request_failed",
            method=request.method,
            path=request.url.path,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        raise

    response.headers["x-request-id"] = request_id
    get_logger().info(
        "request_completed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
    )
    return response
