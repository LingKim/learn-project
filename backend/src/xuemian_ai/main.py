from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse

from xuemian_ai.api.ai_quality import router as quality_router
from xuemian_ai.api.auth import router as auth_router
from xuemian_ai.api.documents import router as documents_router
from xuemian_ai.api.files import router as files_router
from xuemian_ai.api.health import router as health_router
from xuemian_ai.api.learning import router as learning_router
from xuemian_ai.api.learning_assets import router as learning_assets_router
from xuemian_ai.api.learning_attachments import router as learning_attachments_router
from xuemian_ai.api.practice import router as practice_router
from xuemian_ai.api.profiles import router as profiles_router
from xuemian_ai.api.prompts import router as prompts_router
from xuemian_ai.core.config import get_settings
from xuemian_ai.core.logging import configure_logging, get_logger
from xuemian_ai.core.problem_details import PROBLEM_RESPONSES, register_problem_handlers
from xuemian_ai.core.request_context import CallNext, request_context_middleware
from xuemian_ai.infrastructure.resources import Infrastructure
from xuemian_ai.learning.attachment_limits import AttachmentUploadLimitMiddleware
from xuemian_ai.prompt_management.registry import validate_registry

_logger = get_logger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    validate_registry()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        infrastructure = Infrastructure.create(settings)
        app.state.infrastructure = infrastructure
        _logger.info("application_started", app_version=settings.app_version)
        try:
            yield
        finally:
            try:
                await infrastructure.close()
            finally:
                _logger.info("application_stopped", app_version=settings.app_version)

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        responses=PROBLEM_RESPONSES,
        docs_url=None,
        redoc_url=None,
    )

    @application.get("/docs", include_in_schema=False)
    async def swagger_ui() -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url="./openapi.json",
            title=f"{application.title} - Swagger UI",
        )

    @application.get("/redoc", include_in_schema=False)
    async def redoc() -> HTMLResponse:
        return get_redoc_html(
            openapi_url="./openapi.json",
            title=f"{application.title} - ReDoc",
        )

    application.add_middleware(
        AttachmentUploadLimitMiddleware, path=f"{settings.api_v1_prefix}/learning/attachments"
    )
    application.middleware("http")(request_context_middleware)

    @application.middleware("http")
    async def sensitive_cache_policy(request: Request, call_next: CallNext) -> Response:
        response = await call_next(request)
        sensitive_paths = (
            "/ai-quality-cases",
            "/admin/ai-quality",
            "/admin/prompt-definitions",
            "/admin/prompt-versions",
        )
        if any(
            request.url.path == settings.api_v1_prefix + path
            or request.url.path.startswith(settings.api_v1_prefix + path + "/")
            for path in sensitive_paths
        ):
            # 包括认证/授权/冲突等异常响应，不能仅在成功route里设置缓存策略。
            response.headers["Cache-Control"] = "no-store"
        return response

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
    )
    register_problem_handlers(application)
    application.include_router(health_router, prefix=settings.api_v1_prefix)
    application.include_router(auth_router, prefix=settings.api_v1_prefix)
    application.include_router(quality_router, prefix=settings.api_v1_prefix)
    application.include_router(files_router, prefix=settings.api_v1_prefix)
    application.include_router(profiles_router, prefix=settings.api_v1_prefix)
    application.include_router(documents_router, prefix=settings.api_v1_prefix)
    application.include_router(learning_attachments_router, prefix=settings.api_v1_prefix)
    application.include_router(learning_router, prefix=settings.api_v1_prefix)
    application.include_router(practice_router, prefix=settings.api_v1_prefix)
    application.include_router(prompts_router, prefix=settings.api_v1_prefix)
    application.include_router(learning_assets_router, prefix=settings.api_v1_prefix)
    return application


app = create_app()


def run() -> None:
    uvicorn.run(
        "xuemian_ai.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        access_log=False,
        log_config=None,
    )


if __name__ == "__main__":
    run()
