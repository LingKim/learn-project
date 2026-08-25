import asyncio
import json
import logging
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pytest import CaptureFixture
from structlog.contextvars import get_contextvars

from xuemian_ai.api.health import _probe
from xuemian_ai.core.config import Settings
from xuemian_ai.core.errors import NotFoundError
from xuemian_ai.core.logging import configure_logging, get_logger
from xuemian_ai.core.problem_details import register_problem_handlers
from xuemian_ai.core.request_context import request_context_middleware, resolve_request_id
from xuemian_ai.main import create_app


def json_events(captured: CaptureFixture[str]) -> list[dict[str, Any]]:
    return [json.loads(line) for line in captured.readouterr().out.splitlines() if line]


def json_settings(*, log_level: str = "INFO") -> Settings:
    return Settings(  # type: ignore[arg-type]
        environment="test",
        log_format="json",
        log_level=log_level,
    )


def test_structlog_and_standard_logging_share_json_schema(
    capsys: CaptureFixture[str],
) -> None:
    configure_logging(json_settings())

    get_logger("tests.business").info("business_event", result="ok")
    logging.getLogger("tests.foreign").warning("foreign_event")

    events = json_events(capsys)
    assert [event["event"] for event in events] == ["business_event", "foreign_event"]
    for event in events:
        assert event["timestamp"]
        assert event["level"] in {"info", "warning"}
        assert event["logger"] in {"tests.business", "tests.foreign"}
        assert event["service"] == "学面通AI API"
        assert event["environment"] == "test"


def test_log_level_filters_lower_priority_events(capsys: CaptureFixture[str]) -> None:
    configure_logging(json_settings(log_level="WARNING"))
    logger = get_logger("tests.level")

    logger.info("filtered_event")
    logger.error("visible_event")

    assert [event["event"] for event in json_events(capsys)] == ["visible_event"]


def test_console_renderer_keeps_event_and_common_fields(capsys: CaptureFixture[str]) -> None:
    configure_logging(Settings(environment="test", log_format="console", log_level="INFO"))

    get_logger("tests.console").info("console_event")

    output = capsys.readouterr().out
    assert "console_event" in output
    assert "tests.console" in output
    assert "学面通AI API" in output
    assert "environment=test" in output


def test_sensitive_fields_and_text_are_redacted(capsys: CaptureFixture[str]) -> None:
    configure_logging(json_settings())

    get_logger("tests.security").info(
        "security_event",
        credentials={"Password": "plain", "nested": [{"apiKey": "model-key"}]},
        note="Bearer abc.def password=plain postgresql://app:db-secret@localhost/db",
    )

    output = capsys.readouterr().out
    event = json.loads(output)
    assert "plain" not in output
    assert "model-key" not in output
    assert "abc.def" not in output
    assert "db-secret" not in output
    assert event["credentials"]["Password"] == "[REDACTED]"
    assert event["credentials"]["nested"][0]["apiKey"] == "[REDACTED]"


def test_exception_log_contains_only_safe_diagnostics(capsys: CaptureFixture[str]) -> None:
    configure_logging(json_settings())

    try:
        raise RuntimeError("password=plain must not leak")
    except RuntimeError:
        get_logger("tests.exception").error("unhandled_exception", exc_info=True)

    output = capsys.readouterr().out
    event = json.loads(output)
    assert "plain" not in output
    assert "must not leak" not in output
    assert event["exception_type"] == "RuntimeError"
    assert event["stack"][-1]["filename"] == "test_logging.py"
    assert "exc_info" not in event


def test_foreign_exception_uses_same_safe_diagnostics(capsys: CaptureFixture[str]) -> None:
    configure_logging(json_settings())

    try:
        raise RuntimeError("token=foreign-private-value")
    except RuntimeError:
        logging.getLogger("tests.foreign.exception").exception("foreign_failed")

    output = capsys.readouterr().out
    event = json.loads(output)
    assert "foreign-private-value" not in output
    assert event["event"] == "foreign_failed"
    assert event["exception_type"] == "RuntimeError"
    assert event["stack"][-1]["filename"] == "test_logging.py"


def test_request_id_accepts_only_bounded_safe_characters() -> None:
    assert resolve_request_id("gateway.request-1:abc") == "gateway.request-1:abc"

    generated_for_long_value = resolve_request_id("x" * 129)
    generated_for_control_character = resolve_request_id("unsafe\nvalue")
    assert str(UUID(generated_for_long_value)) == generated_for_long_value
    assert str(UUID(generated_for_control_character)) == generated_for_control_character


async def test_concurrent_requests_keep_context_and_route_template(
    capsys: CaptureFixture[str],
) -> None:
    configure_logging(json_settings())
    app = FastAPI()
    app.middleware("http")(request_context_middleware)

    @app.get("/items/{item_id}")
    async def get_item(item_id: str) -> dict[str, str]:
        await asyncio.sleep(0)
        return {"item_id": item_id}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        first, second = await asyncio.gather(
            client.get("/items/private-first", headers={"x-request-id": "request-first"}),
            client.get("/items/private-second", headers={"x-request-id": "request-second"}),
        )

    assert first.headers["x-request-id"] == "request-first"
    assert second.headers["x-request-id"] == "request-second"
    request_events = [
        event for event in json_events(capsys) if event["event"] == "request_completed"
    ]
    assert {event["request_id"] for event in request_events} == {
        "request-first",
        "request-second",
    }
    assert {event["route"] for event in request_events} == {"/items/{item_id}"}
    assert "private-first" not in json.dumps(request_events)
    assert "private-second" not in json.dumps(request_events)
    assert get_contextvars() == {}


async def test_unknown_error_has_one_error_and_one_completion_event(
    capsys: CaptureFixture[str],
) -> None:
    configure_logging(json_settings())
    app = FastAPI()
    app.middleware("http")(request_context_middleware)
    register_problem_handlers(app)

    @app.get("/crash")
    async def crash() -> None:
        raise RuntimeError("token=private-error-value")

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/crash", headers={"x-request-id": "crash-request"})

    events = json_events(capsys)
    assert response.status_code == 500
    assert response.headers["x-request-id"] == "crash-request"
    assert sum(event["event"] == "unhandled_exception" for event in events) == 1
    assert sum(event["event"] == "request_completed" for event in events) == 1
    error = next(event for event in events if event["event"] == "unhandled_exception")
    completion = next(event for event in events if event["event"] == "request_completed")
    assert error["level"] == "error"
    assert error["request_id"] == "crash-request"
    assert error["route"] == "/crash"
    assert completion["status_code"] == 500
    assert "private-error-value" not in json.dumps(events)


async def test_expected_4xx_has_no_separate_warning_or_error(
    capsys: CaptureFixture[str],
) -> None:
    configure_logging(json_settings())
    app = FastAPI()
    app.middleware("http")(request_context_middleware)
    register_problem_handlers(app)

    @app.get("/missing")
    async def missing() -> None:
        raise NotFoundError("不存在", error_key="NOT_FOUND")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/missing")

    events = json_events(capsys)
    assert response.status_code == 404
    assert [event["event"] for event in events] == ["request_completed"]
    assert events[0]["status_code"] == 404


async def test_dependency_failure_log_excludes_exception_message(
    capsys: CaptureFixture[str],
) -> None:
    configure_logging(json_settings())

    async def fail() -> None:
        raise RuntimeError("redis://app:secret@localhost/0")

    name, result = await _probe("redis", fail, 0.1)

    events = json_events(capsys)
    assert name == "redis"
    assert result.status == "down"
    assert len(events) == 1
    assert events[0]["event"] == "dependency_check_failed"
    assert events[0]["dependency"] == "redis"
    assert events[0]["exception_type"] == "RuntimeError"
    assert "secret" not in json.dumps(events)


async def test_application_lifespan_logs_start_and_stop(
    capsys: CaptureFixture[str],
) -> None:
    app = create_app()
    configure_logging(json_settings())

    async with app.router.lifespan_context(app):
        pass

    events = json_events(capsys)
    assert [event["event"] for event in events] == [
        "application_started",
        "application_stopped",
    ]
    assert all(event["app_version"] == "0.1.0" for event in events)
