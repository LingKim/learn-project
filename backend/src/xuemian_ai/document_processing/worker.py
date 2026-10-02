import asyncio
import contextlib
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from xuemian_ai.accounts.models import User
from xuemian_ai.core.config import Settings, get_settings
from xuemian_ai.core.logging import configure_logging, get_logger
from xuemian_ai.document_processing.models import (
    AIProcessingConsent,
    BackgroundTask,
    DocumentChunk,
    DocumentProcessingVersion,
    ProcessingAttempt,
    RetrievalTrace,
    VectorIndexProfile,
    VectorOperation,
)
from xuemian_ai.document_processing.parsers import (
    ParserLimits,
    ProcessingError,
    chunk_nodes,
    complete_ocr,
    extract_document,
)
from xuemian_ai.document_processing.providers import QwenOcrProvider, model_providers
from xuemian_ai.document_processing.service import enqueue_processing, enqueue_vector_cleanup
from xuemian_ai.document_processing.tokenization import tokenize
from xuemian_ai.document_processing.vector_store import VectorStore
from xuemian_ai.file_management.models import FileAsset, KnowledgeBaseFile, StoredObject
from xuemian_ai.file_management.storage import ObjectStorage
from xuemian_ai.infrastructure.resources import Infrastructure

_logger = get_logger(__name__)


@dataclass(frozen=True)
class Claim:
    task_id: UUID
    asset_id: UUID
    user_id: UUID
    token: UUID
    generation: int
    attempt: int
    version_id: UUID
    filename: str
    bucket: str
    object_key: str
    size: int
    sha256: str


class LeaseLost(Exception):
    pass


class TaskCancelled(Exception):
    pass


class DocumentWorker:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        storage: ObjectStorage,
        vector_store: VectorStore,
        settings: Settings,
    ) -> None:
        self.sessions, self.storage, self.vector_store, self.settings = (
            sessions,
            storage,
            vector_store,
            settings,
        )
        self.owner = str(uuid4())
        self._reconcile_after = 0.0
        self._reconcile_cursor: UUID | None = None
        self.embedding, _ = model_providers(settings)
        self.ocr = QwenOcrProvider(settings)
        self.limits = ParserLimits(
            max_characters=settings.document_max_characters,
            max_ocr_pages=settings.document_ocr_max_pages,
            dpi=settings.document_ocr_dpi,
            max_pixels=settings.document_ocr_max_pixels,
            timeout_seconds=settings.document_parse_timeout_seconds,
            chunk_size=settings.document_chunk_size,
            overlap=settings.document_chunk_overlap,
        )

    def profile_key(self) -> str:
        return (
            f"{self.settings.document_provider}:{self.settings.document_embedding_model}:1024:"
            f"{self.settings.qdrant_collection}:v1"
        )

    async def claim(self) -> Claim | None:
        now = datetime.now(UTC)
        eligible = or_(
            and_(BackgroundTask.status == "pending", BackgroundTask.next_attempt_at <= now),
            and_(
                BackgroundTask.status.in_(["processing", "cancel_requested"]),
                BackgroundTask.lease_expires_at <= now,
            ),
        )
        consent = (
            select(AIProcessingConsent.id)
            .where(
                AIProcessingConsent.user_id == BackgroundTask.user_id,
                AIProcessingConsent.terms_version == self.settings.ai_processing_terms_version,
            )
            .exists()
        )
        async with self.sessions() as session:
            candidate = await session.scalar(
                select(BackgroundTask.file_asset_id)
                .where(eligible, consent)
                .order_by(BackgroundTask.created_at)
                .limit(1)
            )
            await session.rollback()
            if candidate is None:
                return None
            async with session.begin():
                asset = await session.scalar(
                    select(FileAsset)
                    .where(FileAsset.id == candidate)
                    .with_for_update(skip_locked=True)
                )
                if asset is None:
                    return None
                task = await session.scalar(
                    select(BackgroundTask)
                    .where(BackgroundTask.file_asset_id == candidate, eligible)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                if task is None:
                    return None
                user = await session.get(User, task.user_id)
                stored = await session.get(StoredObject, asset.stored_object_id)
                cancelled = (
                    task.status == "cancel_requested"
                    or asset.deleted_at is not None
                    or asset.processing_generation != task.input_generation
                    or user is None
                    or user.status != "active"
                    or user.deleted_at is not None
                )
                if task.lease_token is not None:
                    await session.execute(
                        update(ProcessingAttempt)
                        .where(
                            ProcessingAttempt.task_id == task.id,
                            ProcessingAttempt.lease_token == task.lease_token,
                            ProcessingAttempt.ended_at.is_(None),
                        )
                        .values(
                            status="cancelled" if cancelled else "failed",
                            error_code="DOCUMENT_LEASE_EXPIRED",
                            ended_at=now,
                        )
                    )
                    drafts = (
                        await session.scalars(
                            select(DocumentProcessingVersion).where(
                                DocumentProcessingVersion.task_id == task.id,
                                DocumentProcessingVersion.status == "draft",
                            )
                        )
                    ).all()
                    for draft in drafts:
                        draft.status = "cancelled" if cancelled else "failed"
                        await enqueue_vector_cleanup(session, draft)
                if cancelled or task.attempt_count >= task.max_attempts:
                    task.status = "cancelled" if cancelled else "failed"
                    task.ended_at = now
                    task.last_error_code = None if cancelled else "DOCUMENT_LEASE_EXPIRED"
                    task.retryable = not cancelled
                    await self.sync_bindings(session, asset.id, task.status)
                    return None
                if stored is None or stored.status != "available":
                    task.status = "failed"
                    task.last_error_code = "DOCUMENT_SOURCE_UNAVAILABLE"
                    task.ended_at = now
                    await self.sync_bindings(session, asset.id, "failed")
                    return None
                await session.execute(
                    insert(VectorIndexProfile)
                    .values(
                        profile_key=self.profile_key(),
                        provider=self.settings.document_provider,
                        model=self.settings.document_embedding_model,
                        dimensions=1024,
                        distance="Cosine",
                        collection=self.vector_store.collection,
                        schema_version="v1",
                        vector_name="dense",
                    )
                    .on_conflict_do_nothing(index_elements=["profile_key"])
                )
                profile = await session.scalar(
                    select(VectorIndexProfile).where(
                        VectorIndexProfile.profile_key == self.profile_key()
                    )
                )
                assert profile is not None
                number = (
                    int(
                        await session.scalar(
                            select(
                                func.coalesce(func.max(DocumentProcessingVersion.version_number), 0)
                            ).where(DocumentProcessingVersion.file_asset_id == asset.id)
                        )
                        or 0
                    )
                    + 1
                )
                task.status, task.stage = "processing", "downloading"
                task.attempt_count += 1
                task.lease_token = uuid4()
                task.lease_owner = self.owner
                task.lease_expires_at = now + timedelta(
                    seconds=self.settings.document_worker_lease_seconds
                )
                task.started_at = task.started_at or now
                task.last_error_code = None
                task.retryable = False
                task.completed_units = task.total_units = None
                version = DocumentProcessingVersion(
                    user_id=asset.owner_user_id,
                    file_asset_id=asset.id,
                    task_id=task.id,
                    profile_id=profile.id,
                    version_number=number,
                    status="draft",
                    parser_version="pdfium-4.30/docx-1.2/md-4-v1",
                    chunk_strategy_version=f"structure-v1:{self.limits.chunk_size}:{self.limits.overlap}",
                    ocr_strategy_version=f"{self.settings.document_ocr_model}-v1",
                )
                session.add(version)
                session.add(
                    ProcessingAttempt(
                        task_id=task.id,
                        attempt_number=task.attempt_count,
                        lease_token=task.lease_token,
                        status="processing",
                        started_at=now,
                    )
                )
                await session.flush()
                await self.sync_bindings(session, asset.id, "processing")
                return Claim(
                    task.id,
                    asset.id,
                    asset.owner_user_id,
                    task.lease_token,
                    task.input_generation,
                    task.attempt_count,
                    version.id,
                    asset.original_filename,
                    stored.bucket,
                    stored.object_key,
                    asset.byte_size,
                    stored.sha256,
                )

    async def sync_bindings(
        self, session: AsyncSession, asset_id: UUID, status: str, code: str | None = None
    ) -> None:
        active = await session.scalar(
            select(DocumentProcessingVersion.id).where(
                DocumentProcessingVersion.file_asset_id == asset_id,
                DocumentProcessingVersion.status == "active",
            )
        )
        visible = (
            "succeeded" if active else "pending_processing" if status == "cancelled" else status
        )
        await session.execute(
            update(KnowledgeBaseFile)
            .where(
                KnowledgeBaseFile.file_asset_id == asset_id, KnowledgeBaseFile.deleted_at.is_(None)
            )
            .values(processing_status=visible, processing_failure_code=code)
        )

    async def checkpoint(
        self,
        claim: Claim,
        stage: str | None = None,
        completed: int | None = None,
        total: int | None = None,
    ) -> None:
        now = datetime.now(UTC)
        async with self.sessions() as session, session.begin():
            task = await session.scalar(
                select(BackgroundTask).where(BackgroundTask.id == claim.task_id).with_for_update()
            )
            if (
                task is None
                or task.lease_token != claim.token
                or task.lease_expires_at is None
                or task.lease_expires_at <= now
                or task.status not in {"processing", "cancel_requested"}
            ):
                raise LeaseLost()
            if task.status == "cancel_requested":
                raise TaskCancelled()
            task.lease_expires_at = now + timedelta(
                seconds=self.settings.document_worker_lease_seconds
            )
            if stage is not None:
                task.stage, task.completed_units, task.total_units = stage, completed, total

    async def heartbeat(self, claim: Claim, operation: asyncio.Task[None]) -> None:
        while True:
            await asyncio.sleep(self.settings.document_worker_lease_seconds / 3)
            try:
                await self.checkpoint(claim)
            except (LeaseLost, TaskCancelled):
                operation.cancel()
                return
            except Exception:
                operation.cancel()
                return

    async def process(self, claim: Claim) -> None:
        payload = await self.storage.read_and_hash(claim.bucket, claim.object_key, claim.size)
        if payload.sha256 != claim.sha256 or payload.byte_size != claim.size:
            raise ProcessingError("DOCUMENT_SOURCE_CHANGED")
        await self.checkpoint(claim, "extracting")
        document = await extract_document(payload.content, claim.filename, self.limits)

        async def progress(completed: int, total: int) -> None:
            await self.checkpoint(claim, "ocr", completed, total)

        if document.ocr_pages:
            async with asyncio.timeout(self.settings.document_parse_timeout_seconds):
                await complete_ocr(document, self.ocr, self.limits, progress)
        await self.checkpoint(claim, "chunking")
        nodes = chunk_nodes(document, claim.version_id, self.limits)
        if len(nodes) > self.settings.document_max_chunks:
            raise ProcessingError("DOCUMENT_CHUNK_LIMIT_EXCEEDED")
        async with self.sessions() as session, session.begin():
            # 再次 fencing 检查防止过期尝试写入自己的草稿。
            task = await session.scalar(
                select(BackgroundTask).where(BackgroundTask.id == claim.task_id).with_for_update()
            )
            if task is None or task.lease_token != claim.token or task.status != "processing":
                raise LeaseLost()
            version = await session.get(DocumentProcessingVersion, claim.version_id)
            assert version is not None
            version.character_count = sum(len(b.text) for b in document.blocks)
            version.chunk_count, version.image_count = len(nodes), document.image_count
            version.unrecognized_image_count = document.image_count
            version.native_page_count, version.ocr_page_count = (
                document.native_page_count,
                document.ocr_page_count,
            )
            for i, (node, block) in enumerate(nodes):
                session.add(
                    DocumentChunk(
                        id=UUID(node.node_id),
                        processing_version_id=claim.version_id,
                        file_asset_id=claim.asset_id,
                        user_id=claim.user_id,
                        ordinal=i,
                        content=node.text,
                        content_digest=__import__("hashlib").sha256(node.text.encode()).hexdigest(),
                        source_kind=block.source_kind,
                        page_start=block.page,
                        page_end=block.page,
                        paragraph_start=block.paragraph_start,
                        paragraph_end=block.paragraph_end,
                        heading_path=list(block.headings),
                        ocr_confidence=block.confidence,
                        search_vector=func.to_tsvector("simple", tokenize(node.text)),
                    )
                )
        await self.vector_store.check_schema()
        for start in range(0, len(nodes), 20):
            batch = nodes[start : start + 20]
            await self.checkpoint(claim, "embedding", start, len(nodes))
            vectors = await self.embedding.embed([node.text for node, _ in batch])
            await self.checkpoint(claim, "indexing", start, len(nodes))
            await self.vector_store.upsert(
                claim.user_id,
                claim.asset_id,
                claim.version_id,
                [
                    (UUID(node.node_id), vector)
                    for (node, _), vector in zip(batch, vectors, strict=True)
                ],
            )
        if await self.vector_store.count(claim.user_id, claim.asset_id, claim.version_id) != len(
            nodes
        ):
            raise ProcessingError("DOCUMENT_VECTOR_COUNT_MISMATCH", retryable=True)
        await self.checkpoint(claim, "publishing")
        await self.publish(claim)

    async def publish(self, claim: Claim) -> None:
        now = datetime.now(UTC)
        async with self.sessions() as session, session.begin():
            asset = await session.scalar(
                select(FileAsset).where(FileAsset.id == claim.asset_id).with_for_update()
            )
            task = await session.scalar(
                select(BackgroundTask).where(BackgroundTask.id == claim.task_id).with_for_update()
            )
            user = await session.get(User, claim.user_id)
            if (
                asset is None
                or task is None
                or task.lease_token != claim.token
                or task.lease_expires_at is None
                or task.lease_expires_at <= now
                or task.status != "processing"
            ):
                raise LeaseLost()
            if (
                asset.deleted_at is not None
                or asset.processing_generation != claim.generation
                or user is None
                or user.status != "active"
                or user.deleted_at is not None
            ):
                raise TaskCancelled()
            version = await session.get(DocumentProcessingVersion, claim.version_id)
            if version is None or version.status != "draft":
                raise LeaseLost()
            old = (
                await session.scalars(
                    select(DocumentProcessingVersion).where(
                        DocumentProcessingVersion.file_asset_id == asset.id,
                        DocumentProcessingVersion.status == "active",
                    )
                )
            ).all()
            for previous in old:
                previous.status = "retired"
                await enqueue_vector_cleanup(session, previous)
            await session.flush()
            version.status, version.published_at = "active", now
            task.status, task.result_reference, task.ended_at = "succeeded", version.id, now
            task.completed_units = task.total_units = version.chunk_count
            task.lease_expires_at = None
            await session.execute(
                update(ProcessingAttempt)
                .where(
                    ProcessingAttempt.task_id == task.id,
                    ProcessingAttempt.lease_token == claim.token,
                )
                .values(status="succeeded", ended_at=now)
            )
            await session.flush()
            await self.sync_bindings(session, asset.id, "succeeded")

    async def fail(
        self, claim: Claim, error: ProcessingError | None, *, cancelled: bool = False
    ) -> None:
        now = datetime.now(UTC)
        async with self.sessions() as session, session.begin():
            asset = await session.scalar(
                select(FileAsset).where(FileAsset.id == claim.asset_id).with_for_update()
            )
            task = await session.scalar(
                select(BackgroundTask).where(BackgroundTask.id == claim.task_id).with_for_update()
            )
            if (
                task is None
                or task.lease_token != claim.token
                or task.status not in {"processing", "cancel_requested"}
            ):
                return
            cancelled = (
                cancelled
                or task.status == "cancel_requested"
                or asset is None
                or asset.deleted_at is not None
            )
            version = await session.get(DocumentProcessingVersion, claim.version_id)
            code = error.code if error else None
            if version is not None:
                version.status = "cancelled" if cancelled else "failed"
                version.failure_code = code
                await enqueue_vector_cleanup(session, version)
            task.retryable = bool(error and error.retryable) and not cancelled
            task.status = (
                "cancelled"
                if cancelled
                else "pending"
                if task.retryable and task.attempt_count < task.max_attempts
                else "failed"
            )
            task.last_error_code = code
            task.stage = "waiting" if task.status == "pending" else task.stage
            task.next_attempt_at = now + timedelta(seconds=2**task.attempt_count)
            task.ended_at = now if task.status != "pending" else None
            task.lease_expires_at = None
            await session.execute(
                update(ProcessingAttempt)
                .where(
                    ProcessingAttempt.task_id == task.id,
                    ProcessingAttempt.lease_token == claim.token,
                )
                .values(
                    status="cancelled" if cancelled else "failed", error_code=code, ended_at=now
                )
            )
            await self.sync_bindings(session, claim.asset_id, task.status, code)

    async def run_once(self) -> bool:
        claim = await self.claim()
        if claim is None:
            return False
        operation = asyncio.create_task(self.process(claim))
        heartbeat = asyncio.create_task(self.heartbeat(claim, operation))
        try:
            await operation
        except LeaseLost:
            pass
        except TaskCancelled:
            await self.fail(claim, None, cancelled=True)
        except asyncio.CancelledError:
            await self.fail(claim, ProcessingError("DOCUMENT_LEASE_INTERRUPTED", retryable=True))
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise
        except ProcessingError as exc:
            await self.fail(claim, exc)
            _logger.warning("document_processing_failed", error_key=exc.code)
        except Exception:
            await self.fail(
                claim, ProcessingError("DOCUMENT_PROCESSING_UNAVAILABLE", retryable=True)
            )
            _logger.warning(
                "document_processing_failed", error_key="DOCUMENT_PROCESSING_UNAVAILABLE"
            )
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat
        return True

    async def maintenance(self) -> None:
        now = datetime.now(UTC)
        async with self.sessions() as session, session.begin():
            # 为部署前已经校验的资料补齐首次任务；已有历史任务不被自动重启。
            untouched = (
                select(BackgroundTask.id)
                .where(BackgroundTask.file_asset_id == FileAsset.id)
                .exists()
            )
            assets = (
                await session.scalars(
                    select(FileAsset)
                    .where(
                        FileAsset.purpose == "knowledge_document",
                        FileAsset.validation_status == "available",
                        FileAsset.deleted_at.is_(None),
                        ~untouched,
                        select(KnowledgeBaseFile.id)
                        .where(
                            KnowledgeBaseFile.file_asset_id == FileAsset.id,
                            KnowledgeBaseFile.deleted_at.is_(None),
                        )
                        .exists(),
                    )
                    .with_for_update(skip_locked=True)
                    .limit(10)
                )
            ).all()
            for asset in assets:
                await enqueue_processing(session, asset)
            await session.execute(
                delete(RetrievalTrace).where(
                    RetrievalTrace.expires_at <= now, RetrievalTrace.retained_by_case.is_(False)
                )
            )
            operation = await session.scalar(
                select(VectorOperation)
                .where(VectorOperation.status == "pending", VectorOperation.next_attempt_at <= now)
                .order_by(VectorOperation.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if operation is None:
                return
            # 提交领取再调用外部服务；崩溃后到期重新执行幂等删除。
            operation_id = operation.id
            user_id, asset_id, version_id, collection = (
                operation.user_id,
                operation.file_asset_id,
                operation.processing_version_id,
                operation.collection,
            )
            operation.next_attempt_at = now + timedelta(minutes=5)
        store = self.vector_store
        if collection != store.collection:
            store = VectorStore(self.settings.model_copy(update={"qdrant_collection": collection}))
        error = None
        try:
            await store.delete_version(user_id, asset_id, version_id)
        except ProcessingError as exc:
            error = exc
        finally:
            if store is not self.vector_store:
                await store.close()
        async with self.sessions() as session, session.begin():
            operation = await session.get(VectorOperation, operation_id, with_for_update=True)
            if operation is None or operation.status != "pending":
                return
            if error is None:
                await session.execute(
                    delete(DocumentChunk).where(DocumentChunk.processing_version_id == version_id)
                )
                operation.status = "succeeded"
                operation.last_error_code = None
            else:
                operation.attempt_count += 1
                operation.last_error_code = error.code
                operation.next_attempt_at = datetime.now(UTC) + timedelta(
                    seconds=min(3600, 2**operation.attempt_count)
                )
                if operation.attempt_count >= 8:
                    operation.status = "failed"
                    _logger.error("document_vector_cleanup_failed", error_key=error.code)

    async def reconcile(self) -> None:
        """周期逐版本对账；缺失点创建新草稿，当前活动版不直接覆盖。"""
        if time.monotonic() < self._reconcile_after:
            return
        self._reconcile_after = time.monotonic() + 60
        async with self.sessions() as session:
            query = (
                select(DocumentProcessingVersion)
                .join(VectorIndexProfile)
                .where(
                    VectorIndexProfile.collection == self.vector_store.collection,
                    DocumentProcessingVersion.status != "draft",
                )
                .order_by(DocumentProcessingVersion.id)
                .limit(1)
            )
            if self._reconcile_cursor is not None:
                query = query.where(DocumentProcessingVersion.id > self._reconcile_cursor)
            version = await session.scalar(query)
            if version is None:
                self._reconcile_cursor = None
                return
            self._reconcile_cursor = version.id
            identity = (version.user_id, version.file_asset_id, version.id)
            status = version.status
            expected = set(
                (
                    await session.scalars(
                        select(DocumentChunk.id).where(
                            DocumentChunk.processing_version_id == version.id
                        )
                    )
                ).all()
            )
        if status != "active":
            # 旧 worker 延迟写入也会在下一次对账中再次删除。
            await self.vector_store.delete_version(*identity)
            return
        actual = await self.vector_store.version_point_ids(*identity, maximum=100_000)
        await self.vector_store.delete_points(*identity, actual - expected)
        if not expected - actual:
            return
        async with self.sessions() as session, session.begin():
            asset = await session.get(FileAsset, identity[1], with_for_update=True)
            current = await session.get(DocumentProcessingVersion, identity[2])
            if asset is None or asset.deleted_at is not None or current is None:
                return
            if current.status != "active":
                return
            await enqueue_processing(session, asset)
            _logger.warning("document_vector_repair_queued", error_key="DOCUMENT_VECTOR_MISSING")


async def serve() -> None:
    settings = get_settings()
    configure_logging(settings)
    infra = Infrastructure.create(settings)
    store = VectorStore(settings)
    worker = DocumentWorker(infra.sessions, infra.object_storage, store, settings)
    try:
        while True:
            try:
                worked = await worker.run_once()
                await worker.maintenance()
                await worker.reconcile()
            except Exception:
                _logger.error(
                    "document_worker_iteration_failed", error_key="DOCUMENT_WORKER_UNAVAILABLE"
                )
                worked = False
            if not worked:
                await asyncio.sleep(settings.document_worker_poll_seconds)
    finally:
        await store.close()
        await infra.close()


def run() -> None:
    asyncio.run(serve())
