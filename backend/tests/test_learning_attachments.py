from datetime import UTC, datetime, timedelta
from io import BytesIO
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from docx import Document
from PIL import Image

from xuemian_ai.core.config import Settings
from xuemian_ai.core.errors import (
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    ValidationAppError,
)
from xuemian_ai.file_management.models import FileAsset, StoredObject
from xuemian_ai.learning.attachment_models import LearningAttachment
from xuemian_ai.learning.attachments import AttachmentService, normalize_image, parse_attachment


def image_bytes(format_name="PNG", size=(80, 40)):
    output = BytesIO()
    exif = Image.Exif()
    exif[0x010E] = "private metadata"
    Image.new("RGB", size, "yellow").save(output, format_name, exif=exif)
    return output.getvalue()


def test_normalization_preserves_aspect_and_removes_metadata():
    content = normalize_image(image_bytes(), "png")
    with Image.open(BytesIO(content)) as image:
        assert image.format == "WEBP"
        assert image.size == (80, 40)
        assert not image.getexif()


def test_image_type_and_dimensions_are_checked():
    with pytest.raises(ValidationAppError) as mismatch:
        normalize_image(image_bytes(), "jpg")
    assert mismatch.value.error_key == "FILE_TYPE_MISMATCH"
    with pytest.raises(ValidationAppError):
        normalize_image(image_bytes(size=(8193, 1)), "png")
    with pytest.raises(ValidationAppError):
        normalize_image(b"not an image", "png")


@pytest.mark.parametrize(
    "filename, content",
    [("x.png", b"x" * (5 * 1024 * 1024 + 1)), ("x.txt", b"x" * (10 * 1024 * 1024 + 1))],
)
async def test_upload_size_limits(filename, content):
    with pytest.raises(PayloadTooLargeError):
        await parse_attachment(content, filename, Settings())


@pytest.mark.parametrize("extension", ["txt", "md", "markdown", "docx"])
async def test_real_document_body_extracted(extension):
    text = "合成资料：订单编号 SYNTHETIC-42，金额 123 元。"
    if extension == "docx":
        output = BytesIO()
        document = Document()
        document.add_paragraph(text)
        document.save(output)
        content = output.getvalue()
    else:
        content = text.encode()
    _, mime, extracted = await parse_attachment(content, f"test.{extension}", Settings())
    assert text in extracted
    assert not mime.startswith("image/")


async def test_fake_pdf_and_excessive_text_rejected():
    for filename, content in [("fake.pdf", b"not PDF"), ("huge.txt", b"x" * 30001)]:
        with pytest.raises(ValidationAppError):
            await parse_attachment(content, filename, Settings())


async def test_load_rejects_missing_owner_and_already_bound():
    session = AsyncMock()
    scalar_rows = type("Rows", (), {"all": lambda self: []})()
    session.scalars.return_value = scalar_rows
    owner = uuid4()
    service = AttachmentService(None, Settings(), owner, AsyncMock())
    with pytest.raises(NotFoundError):
        await service.load(session, [uuid4()])
    row = LearningAttachment(
        id=uuid4(),
        owner_user_id=owner,
        file_asset_id=uuid4(),
        turn_id=uuid4(),
        extracted_text="body",
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    session.scalars.return_value = type("Rows", (), {"all": lambda self: [row]})()
    with pytest.raises(ConflictError) as sent:
        await service.load(session, [row.id])
    assert sent.value.error_key == "ATTACHMENT_ALREADY_SENT"


async def test_load_bind_is_validated_and_expiry_is_enforced():
    owner, identifier = uuid4(), uuid4()
    row = LearningAttachment(
        id=identifier,
        owner_user_id=owner,
        file_asset_id=uuid4(),
        turn_id=None,
        extracted_text="body",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    session = AsyncMock()
    session.scalars.return_value = type("Rows", (), {"all": lambda self: [row]})()
    service = AttachmentService(None, Settings(), owner, AsyncMock())
    with pytest.raises(ConflictError) as expired:
        await service.load(session, [identifier])
    assert expired.value.error_key == "ATTACHMENT_EXPIRED"
    row.expires_at = datetime.now(UTC) + timedelta(hours=24)
    asset = FileAsset(
        id=row.file_asset_id,
        deleted_at=None,
        stored_object_id=uuid4(),
        validation_status="available",
    )
    stored = StoredObject(id=asset.stored_object_id, status="available")
    session.scalar.side_effect = [asset, stored]
    turn_id = uuid4()
    assert await service.load(session, [identifier], turn_id, bind=True) == [row]
    assert row.turn_id == turn_id


@pytest.mark.parametrize("declared", [None, b"1", b"100"])
async def test_multipart_stream_limit_checks_actual_bytes_and_declared_header(declared):
    import json

    from xuemian_ai.learning.attachment_limits import AttachmentUploadLimitMiddleware

    called = False

    async def app(scope, receive, send):
        nonlocal called
        called = True

    headers = [] if declared is None else [(b"content-length", declared)]
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/learning/attachments",
        "headers": headers,
        "scheme": "http",
        "server": ("localhost", 80),
        "query_string": b"",
    }
    receive = AsyncMock(
        side_effect=[
            {"type": "http.request", "body": b"12345", "more_body": True},
            {"type": "http.request", "body": b"678901", "more_body": False},
        ]
    )
    send = AsyncMock()
    await AttachmentUploadLimitMiddleware(app, path=scope["path"], max_bytes=10)(
        scope, receive, send
    )
    assert not called
    assert send.call_args_list[0].args[0]["status"] == 413
    envelope = json.loads(send.call_args_list[1].args[0]["body"])
    assert envelope["code"] == 413 and envelope["error_key"] == "FILE_TOO_LARGE"
    if declared == b"100":
        receive.assert_not_awaited()


async def test_multipart_stream_limit_accepts_boundary_and_bypasses_other_routes():
    from xuemian_ai.learning.attachment_limits import AttachmentUploadLimitMiddleware

    captured = []

    async def app(scope, receive, send):
        captured.append(await receive())

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/learning/attachments",
        "headers": [],
    }
    receive = AsyncMock(
        return_value={"type": "http.request", "body": b"1234567890", "more_body": False}
    )
    middleware = AttachmentUploadLimitMiddleware(app, path=scope["path"], max_bytes=10)
    await middleware(scope, receive, AsyncMock())
    assert captured[0]["body"] == b"1234567890"
    scope["path"] = "/other"
    receive.return_value["body"] = b"x" * 11
    await middleware(scope, receive, AsyncMock())
    assert captured[1]["body"] == b"x" * 11


async def test_pdf_native_body_and_scan_ocr_are_real_content(monkeypatch):
    from test_document_parsers import native_pdf, scanned_pdf

    from xuemian_ai.document_processing.parsers import OcrResult
    from xuemian_ai.document_processing.providers import QwenOcrProvider

    _, _, native = await parse_attachment(native_pdf(), "native.pdf", Settings())
    assert "PostgreSQL transaction isolation" in native
    recognize = AsyncMock(return_value=OcrResult("合成扫描资料订单编号 SCAN-42"))
    monkeypatch.setattr(QwenOcrProvider, "recognize", recognize)
    _, _, scanned = await parse_attachment(scanned_pdf(), "scan.pdf", Settings())
    assert "SCAN-42" in scanned
    recognize.assert_awaited_once()
    assert recognize.call_args.args[0].startswith(b"\x89PNG")
