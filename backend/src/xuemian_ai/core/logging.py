import logging
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import TracebackType
from typing import Any, cast

import structlog
import structlog.contextvars
from structlog.typing import EventDict, Processor, WrappedLogger

from xuemian_ai.core.config import Settings

REDACTED = "[REDACTED]"

_SENSITIVE_KEY_PARTS = frozenset(
    {
        "access_key",
        "answer",
        "api_key",
        "audio",
        "authorization",
        "body",
        "content",
        "cookie",
        "headers",
        "jd",
        "password",
        "prompt",
        "query",
        "query_string",
        "recording",
        "resume",
        "secret",
        "token",
        "transcript",
    }
)
_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?i)\b(password|token|secret|api[-_]?key|access[-_]?key|authorization|cookie)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_URL_PASSWORD = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://[^:/\s]+:)([^@\s]+)(@)")


def _is_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
    collapsed = normalized.replace("_", "")
    return any(
        part in normalized or part.replace("_", "") in collapsed for part in _SENSITIVE_KEY_PARTS
    )


def _redact_text(value: str) -> str:
    redacted = _BEARER_TOKEN.sub(f"Bearer {REDACTED}", value)
    redacted = _URL_PASSWORD.sub(rf"\1{REDACTED}\3", redacted)
    return _CREDENTIAL_ASSIGNMENT.sub(rf"\1\2{REDACTED}", redacted)


def _redact_value(value: Any, *, key: str | None = None) -> Any:
    if key is not None and _is_sensitive_key(key):
        return REDACTED
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, Mapping):
        return {
            str(nested_key): _redact_value(nested_value, key=str(nested_key))
            for nested_key, nested_value in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return [_redact_value(item) for item in value]
    return f"<{type(value).__name__}>"


def redact_sensitive_data(
    _logger: WrappedLogger,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """在最终渲染前递归移除禁止进入日志的内容。"""

    return cast(EventDict, _redact_value(event_dict))


def _normalize_exc_info(
    exc_info: object,
) -> tuple[type[BaseException], BaseException, TracebackType | None] | None:
    if exc_info is True:
        current = sys.exc_info()
        if current[0] is not None and current[1] is not None:
            return current
        return None
    if isinstance(exc_info, BaseException):
        return type(exc_info), exc_info, exc_info.__traceback__
    if (
        isinstance(exc_info, tuple)
        and len(exc_info) == 3
        and isinstance(exc_info[0], type)
        and issubclass(exc_info[0], BaseException)
        and isinstance(exc_info[1], BaseException)
        and (exc_info[2] is None or isinstance(exc_info[2], TracebackType))
    ):
        return exc_info
    return None


def add_safe_exception(
    _logger: WrappedLogger,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """把 exc_info 转换为不含异常原文和局部变量的安全堆栈。"""

    exc_info = event_dict.pop("exc_info", None)
    normalized = _normalize_exc_info(exc_info)
    if normalized is None:
        return event_dict

    _exception_type, exception, _traceback = normalized
    event_dict.update(safe_exception_fields(exception))
    return event_dict


def safe_exception_fields(exception: BaseException) -> dict[str, object]:
    """返回不含异常消息、源代码文本和局部变量的诊断字段。"""

    stack: list[dict[str, str | int]] = []
    traceback = exception.__traceback__
    while traceback is not None:
        frame = traceback.tb_frame
        stack.append(
            {
                "filename": Path(frame.f_code.co_filename).name,
                "function": frame.f_code.co_name,
                "lineno": traceback.tb_lineno,
            }
        )
        traceback = traceback.tb_next
    return {"exception_type": type(exception).__name__, "stack": stack}


def _add_static_fields(service: str, environment: str) -> Processor:
    def add_fields(
        _logger: WrappedLogger,
        _method_name: str,
        event_dict: EventDict,
    ) -> EventDict:
        event_dict["service"] = service
        event_dict["environment"] = environment
        return event_dict

    return add_fields


def configure_logging(settings: Settings) -> None:
    """配置标准库与 structlog，共享安全的结构化输出。"""

    structlog.contextvars.clear_contextvars()
    level = logging.getLevelNamesMapping()[settings.log_level]
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        _add_static_fields(settings.app_name, settings.environment),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        add_safe_exception,
        redact_sensitive_data,
    ]

    renderer: Processor
    if settings.log_format == "json":
        renderer = structlog.processors.JSONRenderer(ensure_ascii=False)
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    for logger_name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(level)

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False
    access_logger.disabled = True

    for logger_name in ("httpcore", "httpx", "sqlalchemy.engine"):
        logging.getLogger(logger_name).setLevel(max(level, logging.WARNING))

    logging.captureWarnings(True)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))


def bind_context(*, request_id: str) -> None:
    structlog.contextvars.bind_contextvars(request_id=request_id)


def clear_context() -> None:
    structlog.contextvars.clear_contextvars()
