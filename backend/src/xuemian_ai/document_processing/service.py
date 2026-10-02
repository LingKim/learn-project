from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from xuemian_ai.accounts.models import User
from xuemian_ai.core.config import Settings
from xuemian_ai.core.errors import ConflictError, NotFoundError
from xuemian_ai.document_processing.models import (
    AIProcessingConsent,
    BackgroundTask,
    DocumentProcessingVersion,
    VectorIndexProfile,
    VectorOperation,
)
from xuemian_ai.document_processing.schemas import (
    AIConsentView,
    ProcessingTaskView,
    ProcessingVersionView,
)
from xuemian_ai.file_management.models import FileAsset, KnowledgeBaseFile
from xuemian_ai.knowledge_bases.models import KnowledgeBase

CONSENT_NOTICE = (
    "解析资料时，需要将待 OCR 的 PDF 页面图片、文档文本及检索问题发送给千问，"
    "用于文字识别、生成向量和重排。请确认您有权处理这些资料。"
)


async def has_consent(session: AsyncSession, user_id: UUID, settings: Settings) -> bool:
    return bool(
        await session.scalar(
            select(AIProcessingConsent.id).where(
                AIProcessingConsent.user_id == user_id,
                AIProcessingConsent.terms_version == settings.ai_processing_terms_version,
            )
        )
    )


async def enqueue_processing(session: AsyncSession, asset: FileAsset) -> BackgroundTask:
    """调用者必须持有 FileAsset 行锁；自动首次解析位于上传创建事务。"""
    task = await session.scalar(
        select(BackgroundTask).where(
            BackgroundTask.file_asset_id == asset.id,
            BackgroundTask.status.in_(["pending", "processing", "cancel_requested"]),
        )
    )
    if task is not None:
        return task
    asset.processing_generation += 1
    task = BackgroundTask(
        user_id=asset.owner_user_id,
        file_asset_id=asset.id,
        input_generation=asset.processing_generation,
        next_attempt_at=datetime.now(UTC),
        status="pending",
        stage="waiting",
        attempt_count=0,
        retryable=False,
    )
    session.add(task)
    await session.flush()
    await session.execute(
        update(KnowledgeBaseFile)
        .where(KnowledgeBaseFile.file_asset_id == asset.id, KnowledgeBaseFile.deleted_at.is_(None))
        .values(processing_status="pending_processing", processing_failure_code=None)
    )
    return task


async def enqueue_vector_cleanup(session: AsyncSession, version: DocumentProcessingVersion) -> None:
    profile = await session.get(VectorIndexProfile, version.profile_id)
    if profile is None:
        return
    await session.execute(
        insert(VectorOperation)
        .values(
            user_id=version.user_id,
            file_asset_id=version.file_asset_id,
            processing_version_id=version.id,
            collection=profile.collection,
            status="pending",
            attempt_count=0,
            next_attempt_at=datetime.now(UTC),
        )
        .on_conflict_do_nothing(constraint="uq_vector_cleanup_version")
    )


async def revoke_processing(session: AsyncSession, asset: FileAsset) -> None:
    asset.processing_generation += 1
    tasks = (
        await session.scalars(
            select(BackgroundTask)
            .where(
                BackgroundTask.file_asset_id == asset.id,
                BackgroundTask.status.in_(["pending", "processing", "cancel_requested"]),
            )
            .with_for_update()
        )
    ).all()
    for task in tasks:
        task.status = "cancelled" if task.status == "pending" else "cancel_requested"
        task.cancel_requested_at = datetime.now(UTC)
    versions = (
        await session.scalars(
            select(DocumentProcessingVersion).where(
                DocumentProcessingVersion.file_asset_id == asset.id
            )
        )
    ).all()
    for version in versions:
        version.status = "retired"
        await enqueue_vector_cleanup(session, version)


class DocumentService:
    def __init__(self, session: AsyncSession, user: User, settings: Settings) -> None:
        self.session, self.user, self.settings = session, user, settings

    async def consent(self, terms_version: str | None = None) -> AIConsentView:
        if terms_version is not None:
            if terms_version != self.settings.ai_processing_terms_version:
                raise ConflictError(
                    "AI 处理说明已更新，请重新确认", error_key="AI_PROCESSING_TERMS_CHANGED"
                )
            await self.session.execute(
                insert(AIProcessingConsent)
                .values(
                    user_id=self.user.id,
                    terms_version=terms_version,
                    confirmed_at=datetime.now(UTC),
                )
                .on_conflict_do_nothing(constraint="uq_ai_processing_consent")
            )
        return AIConsentView(
            confirmed=await has_consent(self.session, self.user.id, self.settings),
            terms_version=self.settings.ai_processing_terms_version,
            notice=CONSENT_NOTICE,
        )

    async def binding(
        self, kb: UUID, file: UUID, *, lock: bool = False
    ) -> tuple[KnowledgeBaseFile, FileAsset]:
        statement = (
            select(KnowledgeBaseFile, FileAsset)
            .join(FileAsset, FileAsset.id == KnowledgeBaseFile.file_asset_id)
            .join(KnowledgeBase, KnowledgeBase.id == KnowledgeBaseFile.knowledge_base_id)
            .where(
                KnowledgeBase.id == kb,
                KnowledgeBase.owner_user_id == self.user.id,
                KnowledgeBase.deleted_at.is_(None),
                KnowledgeBaseFile.id == file,
                KnowledgeBaseFile.deleted_at.is_(None),
                FileAsset.owner_user_id == self.user.id,
                FileAsset.deleted_at.is_(None),
                FileAsset.purpose == "knowledge_document",
            )
        )
        if lock:
            statement = statement.with_for_update(of=FileAsset)
        row = (await self.session.execute(statement)).one_or_none()
        if row is None:
            raise NotFoundError(error_key="KNOWLEDGE_FILE_NOT_FOUND")
        return row[0], row[1]

    async def latest(self, asset: FileAsset) -> BackgroundTask | None:
        return cast(
            BackgroundTask | None,
            await self.session.scalar(
                select(BackgroundTask)
                .where(
                    BackgroundTask.file_asset_id == asset.id, BackgroundTask.user_id == self.user.id
                )
                .order_by(BackgroundTask.created_at.desc(), BackgroundTask.id.desc())
                .limit(1)
            ),
        )

    async def view(
        self, asset: FileAsset, task: BackgroundTask | None
    ) -> ProcessingTaskView | None:
        if task is None:
            return None
        active = await self.session.scalar(
            select(DocumentProcessingVersion).where(
                DocumentProcessingVersion.file_asset_id == asset.id,
                DocumentProcessingVersion.status == "active",
                DocumentProcessingVersion.user_id == self.user.id,
            )
        )
        view = ProcessingTaskView.model_validate(task)
        view.active_version = ProcessingVersionView.model_validate(active) if active else None
        view.requires_ai_consent = not await has_consent(self.session, self.user.id, self.settings)
        return view

    async def get(self, kb: UUID, file: UUID) -> ProcessingTaskView | None:
        _, asset = await self.binding(kb, file)
        return await self.view(asset, await self.latest(asset))

    async def start(self, kb: UUID, file: UUID) -> ProcessingTaskView:
        _, asset = await self.binding(kb, file, lock=True)
        if asset.validation_status != "available":
            raise ConflictError("文件校验尚未完成", error_key="DOCUMENT_NOT_VALIDATED")
        if not await has_consent(self.session, self.user.id, self.settings):
            raise ConflictError(
                "请先确认 AI 资料处理说明", error_key="AI_PROCESSING_CONSENT_REQUIRED"
            )
        task = await enqueue_processing(self.session, asset)
        result = await self.view(asset, task)
        assert result is not None
        return result

    async def cancel(self, kb: UUID, file: UUID) -> ProcessingTaskView | None:
        _, asset = await self.binding(kb, file, lock=True)
        latest = await self.latest(asset)
        if latest is None:
            return None
        task = await self.session.scalar(
            select(BackgroundTask).where(BackgroundTask.id == latest.id).with_for_update()
        )
        assert task is not None
        if task.status in {"pending", "processing", "cancel_requested"}:
            if task.stage == "publishing":
                raise ConflictError("正在发布解析结果，请稍后再试", error_key="DOCUMENT_PUBLISHING")
            task.cancel_requested_at = datetime.now(UTC)
            if task.status == "pending":
                task.status = "cancelled"
                task.ended_at = datetime.now(UTC)
            else:
                task.status = "cancel_requested"
            active = await self.session.scalar(
                select(func.count()).where(
                    DocumentProcessingVersion.file_asset_id == asset.id,
                    DocumentProcessingVersion.status == "active",
                )
            )
            if task.status == "cancelled":
                await self.session.execute(
                    update(KnowledgeBaseFile)
                    .where(
                        KnowledgeBaseFile.file_asset_id == asset.id,
                        KnowledgeBaseFile.deleted_at.is_(None),
                    )
                    .values(processing_status="succeeded" if active else "pending_processing")
                )
            await self.session.flush()
        return await self.view(asset, task)
