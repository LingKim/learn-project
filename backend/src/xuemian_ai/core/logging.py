import logging
import sys
from typing import Any, cast

import structlog

from xuemian_ai.core.config import Settings


def configure_logging(settings: Settings) -> None:
    """配置标准库与 structlog，共享安全的结构化输出。"""

    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO,
        stream=sys.stdout,
        force=True,
    )
    renderer: Any
    if settings.log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger() -> structlog.stdlib.BoundLogger:
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger())
