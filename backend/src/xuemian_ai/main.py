from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from xuemian_ai.api.health import router as health_router
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
    )
    application.middleware("http")(request_context_middleware)
    register_problem_handlers(application)
    application.include_router(health_router, prefix=settings.api_v1_prefix)
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
