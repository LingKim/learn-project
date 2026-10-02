from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse

from xuemian_ai.api.auth import router as auth_router
from xuemian_ai.api.documents import router as documents_router
from xuemian_ai.api.files import router as files_router
from xuemian_ai.api.health import router as health_router
from xuemian_ai.api.profiles import router as profiles_router
from xuemian_ai.core.config import get_settings
from xuemian_ai.core.logging import configure_logging, get_logger
from xuemian_ai.core.problem_details import PROBLEM_RESPONSES, register_problem_handlers
from xuemian_ai.core.request_context import request_context_middleware
from xuemian_ai.infrastructure.resources import Infrastructure

_logger = get_logger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
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

    application.middleware("http")(request_context_middleware)
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
    application.include_router(files_router, prefix=settings.api_v1_prefix)
    application.include_router(profiles_router, prefix=settings.api_v1_prefix)
    application.include_router(documents_router, prefix=settings.api_v1_prefix)
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
