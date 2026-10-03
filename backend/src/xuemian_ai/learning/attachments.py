"""Private, immutable chat attachments; content never enters logs or knowledge indexes."""

import asyncio
import base64
import hashlib
import io
from datetime import UTC, datetime, timedelta
from pathlib import PurePath
from typing import cast
from uuid import UUID, uuid4

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from xuemian_ai.core.config import Settings
from xuemian_ai.core.errors import (
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    ValidationAppError,
)
from xuemian_ai.document_processing.models import AIProcessingConsent
from xuemian_ai.document_processing.parsers import (
    ParserLimits,
    ProcessingError,
    complete_ocr,
    extract_document,
)
from xuemian_ai.document_processing.providers import QwenOcrProvider
from xuemian_ai.document_processing.schemas import EvidenceChunk
from xuemian_ai.file_management.models import (
    FileAsset,
    FileCleanupTask,
    FilePolicyVersion,
    StoredObject,
)
from xuemian_ai.file_management.policy import DEFAULT_RULES
from xuemian_ai.file_management.storage import ObjectStorage
from xuemian_ai.file_management.validation import normalize_filename, validate_content
from xuemian_ai.learning.attachment_models import LearningAttachment
from xuemian_ai.learning.attachment_schemas import LearningAttachmentView
from xuemian_ai.learning.models import LearningConversation, LearningTurn

MIB = 1024 * 1024
IMAGE_EXTENSIONS = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP"}
DOCUMENT_EXTENSIONS = {"pdf", "docx", "txt", "md", "markdown"}
LIMITS = ParserLimits(max_characters=30_000, max_pages=50, max_ocr_pages=10, timeout_seconds=120)


def normalize_image(content: bytes, extension: str) -> bytes:
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format != IMAGE_EXTENSIONS[extension]:
                raise ValidationAppError(
                    "图片真实类型与扩展名不一致", error_key="FILE_TYPE_MISMATCH"
                )
            if image.width > 8192 or image.height > 8192 or image.width * image.height > 20_000_000:
                raise ValidationAppError("图片尺寸超过限制", error_key="ATTACHMENT_IMAGE_LIMIT")
            if getattr(image, "n_frames", 1) != 1:
                raise ValidationAppError(
                    "暂不支持动画图片", error_key="ATTACHMENT_ANIMATION_UNSUPPORTED"
                )
            image.load()
            processed = ImageOps.exif_transpose(image).convert(
                "RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB"
            )
            result = io.BytesIO()
            processed.save(result, "WEBP", quality=90)
            return result.getvalue()
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise ValidationAppError(
            "图片损坏或无法安全解码", error_key="FILE_STRUCTURE_INVALID"
        ) from None


async def parse_attachment(
    content: bytes, filename: str, settings: Settings
) -> tuple[bytes, str, str]:
    extension = PurePath(filename).suffix.lower().lstrip(".")
    if extension not in IMAGE_EXTENSIONS and extension not in DOCUMENT_EXTENSIONS:
        raise ValidationAppError(
            "支持 PNG/JPG/WebP、PDF/DOCX/TXT/Markdown", error_key="FILE_TYPE_NOT_ALLOWED"
        )
    if len(content) > (5 if extension in IMAGE_EXTENSIONS else 10) * MIB:
        raise PayloadTooLargeError(error_key="FILE_TOO_LARGE")
    if not content:
        raise ValidationAppError("文件内容不能为空", error_key="FILE_EMPTY")
    if extension in IMAGE_EXTENSIONS:
        normalized = await asyncio.to_thread(normalize_image, content, extension)
        if len(normalized) > 5 * MIB:
            raise PayloadTooLargeError(error_key="FILE_TOO_LARGE")
        return normalized, "image/webp", ""
    rules = dict(cast(dict[str, object], DEFAULT_RULES["knowledge_document"]))
    rules.update(
        max_bytes=10 * MIB,
        pdf_max_pages=50,
        text_max_characters=30_000,
        docx_max_uncompressed_bytes=50 * MIB,
    )
    parser_filename = (
        str(PurePath(filename).with_suffix(".md")) if extension == "markdown" else filename
    )
    validation = await asyncio.to_thread(validate_content, parser_filename, content, rules)
    try:
        document = await extract_document(content, parser_filename, LIMITS)

        async def progress(current: int, total: int) -> None:
            pass

        if document.ocr_pages:
            await complete_ocr(document, QwenOcrProvider(settings), LIMITS, progress)
        extracted = "\n\n".join(block.text for block in document.blocks)
        if not extracted.strip():
            raise ProcessingError("DOCUMENT_NO_TEXT")
        if len(extracted) > LIMITS.max_characters:
            raise ProcessingError("DOCUMENT_TEXT_LIMIT_EXCEEDED")
        return content, validation.detected_mime, extracted
    except ProcessingError as exc:
        raise ValidationAppError(
            "文档解析失败，请检查内容或拆分文件后重试", error_key=exc.code
        ) from None


class AttachmentService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
        user_id: UUID,
        storage: ObjectStorage | None = None,
    ) -> None:
        self.sessions, self.settings, self.user_id = sessions, settings, user_id
        self.storage = storage or ObjectStorage(settings)

    async def _consent(self, session: AsyncSession) -> None:
        confirmed = await session.scalar(
            select(AIProcessingConsent.id).where(
                AIProcessingConsent.user_id == self.user_id,
                AIProcessingConsent.terms_version == self.settings.learning_consent_version,
            )
        )
        if not confirmed:
            raise ConflictError("请先确认 AI 图片与文档处理说明", error_key="AI_CONSENT_REQUIRED")

    async def upload(self, file: UploadFile) -> LearningAttachmentView:
        async with self.sessions() as session:
            await self._consent(session)
        filename = normalize_filename(file.filename or "")
        content = await file.read(10 * MIB + 1)
        payload, mime, extracted = await parse_attachment(content, filename, self.settings)
        digest = hashlib.sha256(payload).hexdigest()
        bucket = self.settings.rustfs_documents_bucket
        # Generation-specific keys prevent rollback cleanup from deleting a reused object.
        key = f"chat-attachments/{uuid4()}"
        uploaded = False
        committing = False
        try:
            async with self.sessions() as session, session.begin():
                await self._consent(session)
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:value, 0))"),
                    {"value": f"chat_attachments:{digest}:{len(payload)}"},
                )
                stored = await session.scalar(
                    select(StoredObject)
                    .where(
                        StoredObject.storage_domain == "chat_attachments",
                        StoredObject.sha256 == digest,
                        StoredObject.byte_size == len(payload),
                    )
                    .with_for_update()
                )
                if stored is None or stored.status != "available":
                    uploaded = True
                    writing = asyncio.create_task(
                        self.storage.put_bytes(bucket, key, payload, mime)
                    )
                    try:
                        await asyncio.shield(writing)
                    except asyncio.CancelledError:
                        await writing
                        raise
                    if stored is None:
                        stored = StoredObject(
                            storage_domain="chat_attachments",
                            sha256=digest,
                            byte_size=len(payload),
                            detected_mime=mime,
                            bucket=bucket,
                            object_key=key,
                            status="available",
                            reference_count=0,
                        )
                        session.add(stored)
                    else:
                        session.add(
                            FileCleanupTask(
                                task_type="delete_temporary_object",
                                target_type="attachment_object",
                                payload={"bucket": stored.bucket, "object_key": stored.object_key},
                                status="pending",
                                priority=5,
                                attempt_count=0,
                                max_attempts=8,
                                next_attempt_at=datetime.now(UTC),
                                idempotency_key=f"chat-replace:{stored.id}:{stored.generation}",
                            )
                        )
                        stored.object_key, stored.status = key, "available"
                        stored.generation += 1
                        stored.cleared_at = None
                    await session.flush()
                policy = await session.scalar(
                    select(FilePolicyVersion).where(FilePolicyVersion.status == "published")
                )
                if policy is None:
                    raise ConflictError("文件策略未初始化", error_key="FILE_POLICY_UNAVAILABLE")
                asset = FileAsset(
                    owner_user_id=self.user_id,
                    stored_object_id=stored.id,
                    purpose="learning_attachment",
                    original_filename=filename,
                    detected_mime=mime,
                    byte_size=len(payload),
                    validation_status="available",
                    policy_version_id=policy.id,
                    created_by=self.user_id,
                    updated_by=self.user_id,
                )
                session.add(asset)
                stored.reference_count += 1
                await session.flush()
                attachment = LearningAttachment(
                    owner_user_id=self.user_id,
                    file_asset_id=asset.id,
                    extracted_text=extracted,
                    expires_at=datetime.now(UTC) + timedelta(hours=24),
                    created_by=self.user_id,
                    updated_by=self.user_id,
                )
                session.add(attachment)
                await session.flush()
                view = self._view(attachment, asset)
                committing = True
            uploaded = False
            return view
        finally:
            if uploaded:
                # Cleanup survives cancellation and uses its own transaction after rollback.
                async def cleanup() -> None:
                    async with self.sessions() as cleanup_session, cleanup_session.begin():
                        committed = await cleanup_session.scalar(
                            select(StoredObject.id).where(StoredObject.object_key == key)
                        )
                        if committed is not None:
                            return
                        cleanup_session.add(
                            FileCleanupTask(
                                task_type="delete_temporary_object",
                                target_type="attachment_upload",
                                payload={"bucket": bucket, "object_key": key},
                                status="pending",
                                priority=5,
                                attempt_count=0,
                                max_attempts=8,
                                next_attempt_at=datetime.now(UTC),
                                idempotency_key=f"chat-upload-rollback:{key}",
                            )
                        )

                try:
                    await asyncio.shield(cleanup())
                except Exception:
                    # When the database itself is unavailable, remove the new unique object.
                    if not committing:
                        await asyncio.shield(self.storage.delete_object(bucket, key))
                    # Unknown commit outcomes stay for existing orphan reconciliation;
                    # deleting without DB evidence could remove an accepted attachment.

    async def load(
        self,
        session: AsyncSession,
        ids: list[UUID],
        turn_id: UUID | None = None,
        bind: bool = False,
    ) -> list[LearningAttachment]:
        if len(ids) > 6 or len(set(ids)) != len(ids):
            raise ValidationAppError("每轮最多 6 个附件且不可重复", error_key="ATTACHMENT_LIMIT")
        rows = (
            list(
                (
                    await session.scalars(
                        select(LearningAttachment)
                        .where(
                            LearningAttachment.id.in_(ids),
                            LearningAttachment.owner_user_id == self.user_id,
                            LearningAttachment.deleted_at.is_(None),
                        )
                        .order_by(LearningAttachment.id)
                        .with_for_update()
                    )
                ).all()
            )
            if ids
            else []
        )
        if len(rows) != len(ids):
            raise NotFoundError("附件不存在或无权访问", error_key="ATTACHMENT_NOT_FOUND")
        for row in rows:
            if row.turn_id is not None and row.turn_id != turn_id:
                raise ConflictError("附件已用于其他消息", error_key="ATTACHMENT_ALREADY_SENT")
            if row.turn_id is None and row.expires_at <= datetime.now(UTC):
                raise ConflictError("附件已过期，请重新上传", error_key="ATTACHMENT_EXPIRED")
            asset = await session.scalar(
                select(FileAsset).where(FileAsset.id == row.file_asset_id).with_for_update()
            )
            stored = (
                (
                    await session.scalar(
                        select(StoredObject)
                        .where(StoredObject.id == asset.stored_object_id)
                        .with_for_update()
                    )
                )
                if asset
                else None
            )
            if (
                asset is None
                or asset.deleted_at is not None
                or asset.validation_status != "available"
                or stored is None
                or stored.status != "available"
            ):
                raise NotFoundError("附件内容不可用", error_key="ATTACHMENT_NOT_FOUND")
            if bind:
                if turn_id is None:
                    raise ValueError("ATTACHMENT_TURN_REQUIRED")
                row.turn_id = turn_id
        if sum(len(row.extracted_text) for row in rows) > 60_000:
            raise ValidationAppError(
                "附件正文合计超过 60000 字符，请拆分提问", error_key="ATTACHMENT_TEXT_LIMIT"
            )
        mapped = {row.id: row for row in rows}
        return [mapped[identifier] for identifier in ids]

    @staticmethod
    def _view(attachment: LearningAttachment, asset: FileAsset) -> LearningAttachmentView:
        return LearningAttachmentView(
            id=attachment.id,
            filename=asset.original_filename,
            media_type=asset.detected_mime,
            byte_size=asset.byte_size,
            kind="image" if asset.detected_mime.startswith("image/") else "document",
        )

    async def views(
        self, session: AsyncSession, ids: list[UUID], turn_id: UUID
    ) -> list[LearningAttachmentView]:
        rows = await self.load(session, ids, turn_id)
        result = []
        for row in rows:
            asset = await session.get(FileAsset, row.file_asset_id)
            assert asset is not None
            result.append(self._view(row, asset))
        return result

    async def inputs(self, ids: list[UUID], turn_id: UUID) -> list[dict[str, str]]:
        async with self.sessions() as session, session.begin():
            rows = await self.load(session, ids, turn_id)
            result = []
            for row in rows:
                asset = await session.get(FileAsset, row.file_asset_id)
                assert asset is not None
                item = {
                    "id": str(row.id),
                    "filename": asset.original_filename,
                    "text": row.extracted_text,
                }
                if asset.detected_mime.startswith("image/"):
                    stored = await session.get(StoredObject, asset.stored_object_id)
                    assert stored is not None
                    payload = await self.storage.read_and_hash(
                        stored.bucket, stored.object_key, 5 * MIB
                    )
                    if payload.sha256 != stored.sha256:
                        raise ConflictError(
                            "附件内容发生变化", error_key="ATTACHMENT_CONTENT_CHANGED"
                        )
                    item["image_data_url"] = "data:image/webp;base64," + base64.b64encode(
                        payload.content
                    ).decode("ascii")
                result.append(item)
            return result

    async def content(self, identifier: UUID) -> tuple[bytes, str, str]:
        async with self.sessions() as session, session.begin():
            row = await session.get(LearningAttachment, identifier)
            if row is None or row.owner_user_id != self.user_id or row.deleted_at is not None:
                raise NotFoundError("附件不存在", error_key="ATTACHMENT_NOT_FOUND")
            await self.load(session, [identifier], row.turn_id)
            if row.turn_id:
                turn = await session.get(LearningTurn, row.turn_id)
                conversation = (
                    await session.get(LearningConversation, turn.conversation_id) if turn else None
                )
                if (
                    conversation is None
                    or conversation.deleted_at is not None
                    or conversation.user_id != self.user_id
                ):
                    raise NotFoundError("会话不存在", error_key="ATTACHMENT_NOT_FOUND")
            asset = await session.get(FileAsset, row.file_asset_id)
            assert asset is not None
            stored = await session.get(StoredObject, asset.stored_object_id)
            assert stored is not None
            payload = await self.storage.read_and_hash(stored.bucket, stored.object_key, 10 * MIB)
            if payload.sha256 != stored.sha256:
                raise ConflictError("附件内容发生变化", error_key="ATTACHMENT_CONTENT_CHANGED")
            return payload.content, asset.detected_mime, asset.original_filename

    async def evidence(
        self, session: AsyncSession, conversation_id: UUID, ids: list[UUID]
    ) -> dict[UUID, EvidenceChunk]:
        result = {}
        for identifier in ids:
            row = await session.get(LearningAttachment, identifier)
            if row is None or row.turn_id is None:
                raise NotFoundError("附件不存在", error_key="ATTACHMENT_NOT_FOUND")
            await self.load(session, [identifier], row.turn_id)
            turn = await session.get(LearningTurn, row.turn_id)
            if turn is None or turn.conversation_id != conversation_id:
                raise NotFoundError("附件不存在", error_key="ATTACHMENT_NOT_FOUND")
            asset = await session.get(FileAsset, row.file_asset_id)
            assert asset is not None
            result[row.id] = EvidenceChunk(
                chunk_id=row.id,
                file_id=row.id,
                file_name=asset.original_filename,
                processing_version_id=row.id,
                content=row.extracted_text
                or f"用户上传图片：{asset.original_filename}（图像内容随消息另行提供）",
                score=1.0,
                source_kind="user_attachment",
                page_start=None,
                page_end=None,
                paragraph_start=None,
                paragraph_end=None,
                heading_path=[],
                ocr_confidence=None,
            )
        return result

    async def delete(self, identifier: UUID) -> None:
        async with self.sessions() as session, session.begin():
            rows = await self.load(session, [identifier])
            await release_attachment(session, rows[0], self.user_id)

    async def delete_conversation(self, session: AsyncSession, conversation_id: UUID) -> None:
        rows = list(
            (
                await session.scalars(
                    select(LearningAttachment)
                    .join(LearningTurn, LearningTurn.id == LearningAttachment.turn_id)
                    .where(
                        LearningTurn.conversation_id == conversation_id,
                        LearningAttachment.owner_user_id == self.user_id,
                        LearningAttachment.deleted_at.is_(None),
                    )
                    .order_by(LearningAttachment.id)
                    .with_for_update(of=LearningAttachment)
                )
            ).all()
        )
        for row in rows:
            await release_attachment(session, row, self.user_id)


async def release_attachment(
    session: AsyncSession, row: LearningAttachment, user_id: UUID | None = None
) -> None:
    if row.deleted_at is not None:
        return
    now = datetime.now(UTC)
    row.deleted_at, row.deleted_by = now, user_id
    asset = await session.scalar(
        select(FileAsset).where(FileAsset.id == row.file_asset_id).with_for_update()
    )
    if asset is None or asset.deleted_at is not None:
        return
    asset.deleted_at, asset.deleted_by = now, user_id
    stored = await session.scalar(
        select(StoredObject).where(StoredObject.id == asset.stored_object_id).with_for_update()
    )
    if stored is not None:
        stored.reference_count = max(0, stored.reference_count - 1)
        if stored.reference_count == 0:
            stored.status = "deleting"
            session.add(
                FileCleanupTask(
                    task_type="delete_stored_object",
                    target_type="stored_object",
                    target_id=stored.id,
                    payload={"stored_object_id": str(stored.id)},
                    status="pending",
                    priority=5,
                    attempt_count=0,
                    max_attempts=8,
                    next_attempt_at=now,
                    idempotency_key=f"chat-delete:{row.id}:{stored.generation}",
                )
            )


async def expire_attachments(session: AsyncSession, now: datetime) -> None:
    rows = list(
        (
            await session.scalars(
                select(LearningAttachment)
                .where(
                    LearningAttachment.turn_id.is_(None),
                    LearningAttachment.deleted_at.is_(None),
                    LearningAttachment.expires_at <= now,
                )
                .order_by(LearningAttachment.id)
                .with_for_update(skip_locked=True)
                .limit(500)
            )
        ).all()
    )
    for row in rows:
        await release_attachment(session, row)
