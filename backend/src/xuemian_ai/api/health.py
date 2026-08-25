import asyncio
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from xuemian_ai.core.config import Settings, get_settings
from xuemian_ai.core.logging import get_logger
from xuemian_ai.infrastructure.resources import Infrastructure

router = APIRouter(prefix="/health", tags=["system"])
_logger = get_logger(__name__)


class LiveResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "xuemian-ai-backend"


class DependencyCheck(BaseModel):
    status: Literal["up", "down"]
    code: str


class ReadyResponse(BaseModel):
    status: Literal["ready", "degraded"]
    checks: dict[str, DependencyCheck]


async def _probe(
    name: str,
    operation: Callable[[], Awaitable[None]],
    timeout_seconds: float,
) -> tuple[str, DependencyCheck]:
    started_at = perf_counter()
    try:
        await asyncio.wait_for(operation(), timeout=timeout_seconds)
    except Exception as exc:
        _logger.warning(
            "dependency_check_failed",
            dependency=name,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
            exception_type=type(exc).__name__,
        )
        return name, DependencyCheck(status="down", code=f"{name}_unavailable")
    return name, DependencyCheck(status="up", code="ok")


async def run_readiness_checks(
    infrastructure: Infrastructure,
    settings: Settings,
) -> ReadyResponse:
    results = await asyncio.gather(
        _probe(
            "postgresql",
            infrastructure.check_database,
            settings.dependency_timeout_seconds,
        ),
        _probe("redis", infrastructure.check_redis, settings.dependency_timeout_seconds),
        _probe(
            "rustfs",
            lambda: infrastructure.check_rustfs(str(settings.rustfs_health_url)),
            settings.dependency_timeout_seconds,
        ),
    )
    checks = dict(results)
    is_ready = all(check.status == "up" for check in checks.values())
    return ReadyResponse(status="ready" if is_ready else "degraded", checks=checks)


@router.get("/live", operation_id="health_live", response_model=LiveResponse)
async def live() -> LiveResponse:
    return LiveResponse()


@router.get(
    "/ready",
    operation_id="health_ready",
    response_model=ReadyResponse,
    responses={503: {"model": ReadyResponse}},
)
async def ready(request: Request) -> ReadyResponse | JSONResponse:
    settings = get_settings()
    result = await run_readiness_checks(request.app.state.infrastructure, settings)
    if result.status == "degraded":
        return JSONResponse(status_code=503, content=result.model_dump())
    return result
