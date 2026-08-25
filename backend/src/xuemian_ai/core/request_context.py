import re
from collections.abc import Awaitable, Callable
from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response

from xuemian_ai.core.logging import bind_context, clear_context, get_logger

CallNext = Callable[[Request], Awaitable[Response]]

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_logger = get_logger(__name__)


def resolve_request_id(candidate: str | None) -> str:
    if candidate is not None and _REQUEST_ID_PATTERN.fullmatch(candidate) is not None:
        return candidate
    return str(uuid4())


def route_template(request: Request) -> str:
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    return template if isinstance(template, str) else "<unmatched>"


async def request_context_middleware(request: Request, call_next: CallNext) -> Response:
    clear_context()
    request_id = resolve_request_id(request.headers.get("x-request-id"))
    request.state.request_id = request_id
    bind_context(request_id=request_id)

    started_at = perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["x-request-id"] = request_id
        return response
    finally:
        _logger.info(
            "request_completed",
            method=request.method,
            route=route_template(request),
            status_code=status_code,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        clear_context()
