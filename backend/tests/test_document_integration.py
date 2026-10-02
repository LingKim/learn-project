import hashlib
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text, update

from xuemian_ai.accounts.models import User
from xuemian_ai.core.config import get_settings
from xuemian_ai.core.errors import ConflictError, NotFoundError
from xuemian_ai.document_processing.models import (
    AIProcessingConsent,
    BackgroundTask,
    DocumentProcessingVersion,
    ProcessingAttempt,
    RetrievalTrace,
    VectorOperation,
)
from xuemian_ai.document_processing.parsers import ProcessingError
from xuemian_ai.document_processing.retrieval import RetrievalService
from xuemian_ai.document_processing.schemas import RetrievalRequest
from xuemian_ai.document_processing.service import (
    DocumentService,
    enqueue_processing,
    revoke_processing,
)
from xuemian_ai.document_processing.vector_store import VectorStore
from xuemian_ai.document_processing.worker import DocumentWorker, LeaseLost
from xuemian_ai.file_management.models import (
    FileAsset,
    FilePolicyVersion,
    KnowledgeBaseFile,
    StoredObject,
)
from xuemian_ai.file_management.policy import DEFAULT_RULES
from xuemian_ai.file_management.storage import StoredPayload
from xuemian_ai.infrastructure.database import create_database_engine, create_session_factory
from xuemian_ai.knowledge_bases.models import KnowledgeBase

pytestmark = pytest.mark.skipif(
    not os.getenv("DOCUMENT_INTEGRATION_DB"), reason="explicit isolated database required"
)


@pytest_asyncio.fixture
async def context():
    settings = get_settings()
    assert settings.environment == "test" and settings.document_provider == "deterministic"
    engine = create_database_engine(settings.database_url.get_secret_value())
    sessions = create_session_factory(engine)
    async with engine.connect() as c:
        assert (
            await c.scalar(text("SELECT current_database()"))
            == os.environ["DOCUMENT_INTEGRATION_DB"]
        )
    store = VectorStore(settings)
    await store.initialize()
    try:
        yield settings, sessions, store
    finally:
        async with sessions() as session, session.begin():
            await session.execute(delete(VectorOperation))
            await session.execute(delete(User))
            await session.execute(delete(StoredObject))
        await store.client.delete_collection(store.collection)
        await store.close()
        await engine.dispose()


async def seed(
    context,
    content: bytes = b"PostgreSQL transaction isolation prevents dirty reads.",
    *,
    consent: bool = True,
):
    settings, sessions, store = context
    async with sessions() as session, session.begin():
        user = User(
            username="doc" + uuid4().hex[:16],
            nickname="Synthetic learner",
            password_hash="not-a-login-hash",
            status="active",
            role="user",
        )
        session.add(user)
        await session.flush()
        kb = KnowledgeBase(owner_user_id=user.id, name="Synthetic database notes", is_default=True)
        policy = await session.scalar(select(FilePolicyVersion).limit(1))
        if policy is None:
            policy = FilePolicyVersion(version=1, status="published", rules=DEFAULT_RULES)
            session.add(policy)
            await session.flush()
        stored = StoredObject(
            storage_domain="documents",
            sha256=hashlib.sha256(content).hexdigest(),
            byte_size=len(content),
            detected_mime="text/plain",
            bucket="synthetic-only",
            object_key=uuid4().hex,
            status="available",
            reference_count=1,
        )
        session.add_all([kb, stored])
        await session.flush()
        asset = FileAsset(
            owner_user_id=user.id,
            stored_object_id=stored.id,
            purpose="knowledge_document",
            original_filename="fixture.txt",
            detected_mime="text/plain",
            byte_size=len(content),
            validation_status="available",
            policy_version_id=policy.id,
        )
        session.add(asset)
        await session.flush()
        binding = KnowledgeBaseFile(
            knowledge_base_id=kb.id,
            file_asset_id=asset.id,
            display_name="fixture.txt",
            processing_status="pending_processing",
            resource_version=1,
        )
        session.add(binding)
        await session.flush()
        if consent:
            session.add(
                AIProcessingConsent(
                    user_id=user.id,
                    terms_version=settings.ai_processing_terms_version,
                    confirmed_at=datetime.now(UTC),
                )
            )
        task = await enqueue_processing(session, asset)
        ids = (user, kb.id, binding.id, asset.id, task.id)
    storage = AsyncMock()
    storage.read_and_hash.return_value = StoredPayload(
        content, hashlib.sha256(content).hexdigest(), len(content)
    )
    return ids, DocumentWorker(sessions, storage, store, settings)


async def test_real_postgres_qdrant_processing_retrieval_trace_and_owner_isolation(context) -> None:
    (user, kb, file, asset, task), worker = await seed(context)
    settings, sessions, store = context
    assert await worker.run_once()
    async with sessions() as session:
        state = await session.get(BackgroundTask, task)
        assert state.status == "succeeded", state.last_error_code
        version = await session.scalar(
            select(DocumentProcessingVersion).where(DocumentProcessingVersion.status == "active")
        )
        assert version.chunk_count == 1
        view = await DocumentService(session, user, settings).get(kb, file)
        assert view.active_version.id == version.id
    result = await RetrievalService(sessions, settings, user.id, "synthetic-request", store).search(
        kb, RetrievalRequest(query="PostgreSQL transaction isolation")
    )
    assert result.trace_complete and len(result.evidence) == 1
    assert result.evidence[0].file_id == file and result.evidence[0].paragraph_start == 1
    async with sessions() as session:
        trace = await session.get(RetrievalTrace, result.trace_id)
        assert "PostgreSQL" not in str(trace.stages) and "dirty reads" not in str(trace.stages)
        assert len(trace.query_digest) == 64
    with pytest.raises(NotFoundError):
        await RetrievalService(sessions, settings, uuid4(), None, store).search(
            kb, RetrievalRequest(query="transaction")
        )
    noanswer = await RetrievalService(sessions, settings, user.id, None, store).search(
        kb, RetrievalRequest(query="zzzzzzz")
    )
    assert not noanswer.evidence


async def test_consent_gate_and_pending_cancel(context) -> None:
    (user, kb, file, asset, task), worker = await seed(context, consent=False)
    settings, sessions, _ = context
    assert await worker.claim() is None
    worker.storage.read_and_hash.assert_not_awaited()
    async with sessions() as session, session.begin():
        service = DocumentService(session, user, settings)
        with pytest.raises(ConflictError, match="确认"):
            await service.start(kb, file)
        view = await service.cancel(kb, file)
        assert view.status == "cancelled"
    async with sessions() as session:
        binding = await session.get(KnowledgeBaseFile, file)
        assert binding.processing_status == "pending_processing"


async def test_reparse_failure_keeps_active_version_and_cleanup_retries(context) -> None:
    (user, kb, file, asset, task), worker = await seed(context)
    settings, sessions, store = context
    await worker.run_once()
    async with sessions() as session, session.begin():
        original = (await DocumentService(session, user, settings).get(kb, file)).active_version.id
        new = await DocumentService(session, user, settings).start(kb, file)
    worker.embedding = AsyncMock()
    worker.embedding.embed.side_effect = ProcessingError("DOCUMENT_EMBEDDING_AUTH_FAILED")
    await worker.run_once()
    async with sessions() as session:
        view = await DocumentService(session, user, settings).get(kb, file)
        assert view.id == new.id and view.status == "failed"
        assert view.active_version.id == original
    await worker.maintenance()
    result = await RetrievalService(sessions, settings, user.id, None, store).search(
        kb, RetrievalRequest(query="transaction")
    )
    assert result.evidence[0].processing_version_id == original


async def test_expired_lease_cannot_publish_and_history_retained(context) -> None:
    (user, kb, file, asset, task), worker = await seed(context)
    settings, sessions, store = context
    old = await worker.claim()
    async with sessions() as session, session.begin():
        await session.execute(
            update(BackgroundTask)
            .where(BackgroundTask.id == task)
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    other = DocumentWorker(sessions, worker.storage, store, settings)
    fresh = await other.claim()
    assert old.token != fresh.token
    with pytest.raises(LeaseLost):
        await worker.publish(old)
    await other.process(fresh)
    async with sessions() as session:
        attempts = (
            await session.scalars(
                select(ProcessingAttempt)
                .where(ProcessingAttempt.task_id == task)
                .order_by(ProcessingAttempt.attempt_number)
            )
        ).all()
        assert [a.status for a in attempts] == ["failed", "succeeded"]


async def test_move_delete_and_return_recheck(context) -> None:
    (user, kb, file, asset, task), worker = await seed(context)
    settings, sessions, store = context
    await worker.run_once()
    async with sessions() as session, session.begin():
        newkb = KnowledgeBase(owner_user_id=user.id, name="Moved", is_default=False)
        session.add(newkb)
        await session.flush()
        binding = await session.get(KnowledgeBaseFile, file)
        binding.knowledge_base_id = newkb.id
    old = await RetrievalService(sessions, settings, user.id, None, store).search(
        kb, RetrievalRequest(query="transaction")
    )
    assert not old.evidence
    moved = await RetrievalService(sessions, settings, user.id, None, store).search(
        newkb.id, RetrievalRequest(query="transaction")
    )
    assert moved.evidence
    async with sessions() as session, session.begin():
        binding = await session.get(KnowledgeBaseFile, file)
        binding.deleted_at = datetime.now(UTC)
        source = await session.get(FileAsset, asset)
        source.deleted_at = datetime.now(UTC)
        await revoke_processing(session, source)
    deleted = await RetrievalService(sessions, settings, user.id, None, store).search(
        newkb.id, RetrievalRequest(query="transaction")
    )
    assert not deleted.evidence
    await worker.maintenance()
    assert await store.count(user.id, asset, moved.evidence[0].processing_version_id) == 0


async def test_reconciliation_removes_extra_points_and_rebuilds_missing(context) -> None:
    (user, kb, file, asset, task), worker = await seed(context)
    settings, sessions, store = context
    await worker.run_once()
    async with sessions() as session:
        active = await session.scalar(
            select(DocumentProcessingVersion).where(DocumentProcessingVersion.status == "active")
        )
        version = active.id
    expected = await store.version_point_ids(user.id, asset, version, 100)
    extra = uuid4()
    await store.upsert(user.id, asset, version, [(extra, [1.0] * 1024)])
    await worker.reconcile()
    assert await store.version_point_ids(user.id, asset, version, 100) == expected
    await store.delete_points(user.id, asset, version, expected)
    worker._reconcile_after = 0
    worker._reconcile_cursor = None
    await worker.reconcile()
    async with sessions() as session:
        view = await DocumentService(session, user, settings).get(kb, file)
        assert view.status == "pending" and view.active_version.id == version
    assert await worker.run_once()
    async with sessions() as session:
        view = await DocumentService(session, user, settings).get(kb, file)
        assert view.status == "succeeded" and view.active_version.id != version


async def test_concurrent_workers_share_profile_without_double_claim(context) -> None:
    import asyncio

    first, worker = await seed(context)
    second, other = await seed(context, b"Python coroutines use an event loop.")
    claims = await asyncio.gather(worker.claim(), other.claim())
    # skip_locked 可让争用同一候选的 worker 暂时空闲，下一轮领取另一任务。
    for index, claimant in enumerate((worker, other)):
        if claims[index] is None:
            claims[index] = await claimant.claim()
    assert all(claim is not None for claim in claims)
    assert len({claim.task_id for claim in claims}) == 2
    await asyncio.gather(worker.process(claims[0]), other.process(claims[1]))
    _, sessions, _ = context
    async with sessions() as session:
        for task_id in (first[-1], second[-1]):
            task = await session.get(BackgroundTask, task_id)
            assert task.status == "succeeded"


async def test_overview_statistics_and_format_pagination_exclude_private_deleted_data(context):
    from xuemian_ai.file_management.service import FileManagementService

    (user, kb, file, asset, _), _worker = await seed(context)
    (other, other_kb, _, _, _), _other_worker = await seed(context, b"other owner")
    settings, sessions, _store = context
    async with sessions() as session, session.begin():
        binding = await session.get(KnowledgeBaseFile, file)
        binding.display_name = "b.PDF"
        binding.processing_status = "succeeded"
        # Three active files, one deleted binding and one deleted asset.
        rows = []
        for name, status in (
            ("a.pdf", "processing"),
            ("notes.txt", "pending_processing"),
            ("deleted.pdf", "succeeded"),
            ("deleted-asset.pdf", "succeeded"),
        ):
            source = await session.get(FileAsset, asset)
            copy = FileAsset(
                owner_user_id=user.id,
                stored_object_id=source.stored_object_id,
                purpose="knowledge_document",
                original_filename=name,
                detected_mime="text/plain",
                byte_size=source.byte_size,
                validation_status="available",
                policy_version_id=source.policy_version_id,
            )
            session.add(copy)
            await session.flush()
            row = KnowledgeBaseFile(
                knowledge_base_id=kb,
                file_asset_id=copy.id,
                display_name=name,
                processing_status=status,
                resource_version=1,
            )
            session.add(row)
            if name == "deleted.pdf":
                row.deleted_at = datetime.now(UTC)
            if name == "deleted-asset.pdf":
                copy.deleted_at = datetime.now(UTC)
            rows.append(row)
        deleted_base = KnowledgeBase(
            owner_user_id=user.id,
            name="Deleted base",
            is_default=False,
            deleted_at=datetime.now(UTC),
        )
        session.add(deleted_base)
        await session.flush()
        session.add(
            KnowledgeBaseFile(
                knowledge_base_id=deleted_base.id,
                file_asset_id=asset,
                display_name="hidden.pdf",
                processing_status="succeeded",
                resource_version=1,
            )
        )
        await session.flush()
        service = FileManagementService(
            session=session, redis=AsyncMock(), storage=AsyncMock(), settings=settings, user=user
        )
        stats = await service.knowledge_base_statistics()
        assert stats.knowledge_base_count == 1
        assert stats.file_counts == {kb: 3}
        assert stats.available_file_count == 1
        assert stats.processing_file_count == 1
        assert stats.latest_updated_name == "Synthetic database notes"
        first, total = await service.list_files(kb, 1, 1, None, None, "pdf", "name")
        second, second_total = await service.list_files(kb, 2, 1, None, None, "pdf", "name")
        assert total == second_total == 2
        assert [first[0].display_name, second[0].display_name] == ["a.pdf", "b.PDF"]
        filtered, filtered_total = await service.list_files(kb, 1, 20, None, "processing", "pdf")
        assert filtered_total == 1 and filtered[0].display_name == "a.pdf"
        with pytest.raises(NotFoundError):
            await service.list_files(other_kb, 1, 20, None, None)
