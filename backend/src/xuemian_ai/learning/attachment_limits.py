"""Bound multipart bytes before Starlette parses/spools untrusted upload parts."""

from tempfile import SpooledTemporaryFile

from fastapi import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from xuemian_ai.core.errors import PayloadTooLargeError
from xuemian_ai.core.problem_details import _problem


class AttachmentUploadLimitMiddleware:
    def __init__(self, app: ASGIApp, *, path: str, max_bytes: int = 11 * 1024 * 1024) -> None:
        self.app, self.path, self.max_bytes = app, path, max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"].rstrip("/") != self.path
        ):
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = 0
        if declared > self.max_bytes:
            await self._reject(scope, receive, send)
            return
        # Bounded spool enables rejection before the multipart parser creates any file.
        with SpooledTemporaryFile(max_size=1024 * 1024) as spool:
            total = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                total += len(chunk)
                if total > self.max_bytes:
                    await self._reject(scope, receive, send)
                    return
                spool.write(chunk)
                if not message.get("more_body", False):
                    break
            spool.seek(0)
            exhausted = False

            async def replay() -> Message:
                nonlocal exhausted
                if exhausted:
                    return await receive()
                chunk = spool.read(64 * 1024)
                more = spool.tell() < total
                if not more:
                    exhausted = True
                return {"type": "http.request", "body": chunk, "more_body": more}

            await self.app(scope, replay, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        error = PayloadTooLargeError(error_key="FILE_TOO_LARGE")
        response = _problem(
            Request(scope),
            status=error.status_code.value,
            title=error.title,
            message=error.message,
            error_type=error.error_type,
            error_key=error.error_key,
            headers={"Cache-Control": "no-store"},
        )
        await response(scope, receive, send)
