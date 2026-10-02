import asyncio
import os
import re
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from test_document_integration import seed

from xuemian_ai.core.errors import ConflictError, NotFoundError, UpstreamServiceError
from xuemian_ai.document_processing.models import DocumentProcessingVersion
from xuemian_ai.document_processing.retrieval import RetrievalService
from xuemian_ai.document_processing.schemas import RetrievalResult
from xuemian_ai.file_management.models import KnowledgeBaseFile
from xuemian_ai.learning.generation import QwenAnswerProvider
from xuemian_ai.learning.models import LearningTurn
from xuemian_ai.learning.schemas import AnswerRequest, ConversationCreate, GeneratedAnswer
from xuemian_ai.learning.service import LearningService

pytest_plugins = ["test_document_integration"]

pytestmark = pytest.mark.skipif(
    not os.getenv("DOCUMENT_INTEGRATION_DB"), reason="explicit isolated database required"
)


async def setup(context, mode="general"):
    (user, kb, file, _, _), worker = await seed(context)
    settings, sessions, store = context
    await worker.run_once()
    provider = AsyncMock()
    provider.generate.return_value = GeneratedAnswer(
        answer="合成回答" if mode == "general" else "合成资料回答 [1]",
        refused=False,
        citation_ids=[] if mode == "general" else [1],
    )
    retrieval = RetrievalService(sessions, settings, user.id, None, store)
    service = LearningService(sessions, settings, user.id, provider=provider, retrieval=retrieval)
    await service.consent(settings.learning_consent_version)
    conversation = await service.create(
        ConversationCreate(mode=mode, knowledge_base_id=kb if mode == "materials" else None)
    )
    return service, conversation, provider, kb, file


async def test_idempotence_owner_isolation_title_history_and_feedback(context) -> None:
    service, conversation, provider, _, _ = await setup(context)
    body = AnswerRequest(request_key=uuid4(), question="事务是什么？")
    first = await service.answer(conversation.id, body)
    second = await service.answer(conversation.id, body)
    assert first.id == second.id and provider.generate.await_count == 1
    assert first.source_label == "模型通用知识"
    with pytest.raises(ConflictError):
        await service.answer(conversation.id, body.model_copy(update={"language": "en"}))
    detail = await service.detail(conversation.id)
    assert detail.conversation.title == body.question and len(detail.turns) == 1
    assert (await service.feedback(conversation.id, first.id, "helpful")).feedback == "helpful"
    assert (await service.rename(conversation.id, "新标题")).title == "新标题"
    with pytest.raises(ConflictError):
        await service.answer(conversation.id, body.model_copy(update={"question": "不同问题"}))
    stranger = LearningService(service.sessions, service.settings, uuid4(), provider=provider)
    for action in (
        stranger.detail(conversation.id),
        stranger.delete(conversation.id),
        stranger.answer(conversation.id, body),
    ):
        with pytest.raises(NotFoundError):
            await action
    await service.delete(conversation.id)
    assert (await service.list_conversations(1, 20)).meta.total == 0
    with pytest.raises(NotFoundError):
        await service.detail(conversation.id)


async def test_concurrent_answer_and_deleted_conversation_cannot_publish(context) -> None:
    service, conversation, provider, _, _ = await setup(context)
    started, release = asyncio.Event(), asyncio.Event()

    async def blocked(_):
        started.set()
        await release.wait()
        return GeneratedAnswer(answer="合成回答", refused=False, citation_ids=[])

    provider.generate.side_effect = blocked
    request = AnswerRequest(request_key=uuid4(), question="问题")
    running = asyncio.create_task(service.answer(conversation.id, request))
    await started.wait()
    try:
        with pytest.raises(ConflictError, match="正在回答"):
            await service.answer(conversation.id, request)
        await service.delete(conversation.id)
    finally:
        release.set()
    with pytest.raises(NotFoundError):
        await running
    async with service.sessions() as session:
        turn = await session.scalar(
            select(LearningTurn).where(LearningTurn.conversation_id == conversation.id)
        )
        assert turn.status == "failed" and turn.answer is None


async def test_failure_retry_reuses_request_and_expired_lease(context) -> None:
    service, conversation, provider, _, _ = await setup(context)
    body = AnswerRequest(request_key=uuid4(), question="问题")
    provider.generate.side_effect = UpstreamServiceError(error_key="ANSWER_UNAVAILABLE")
    with pytest.raises(UpstreamServiceError):
        await service.answer(conversation.id, body)
    provider.generate.side_effect = None
    answer = await service.answer(conversation.id, body)
    assert answer.status == "succeeded"
    async with service.sessions() as session, session.begin():
        turn = await session.get(LearningTurn, answer.id)
        assert turn.attempt_count == 2
        turn.status = "processing"
        turn.answer = None
        turn.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    expired = await service.detail(conversation.id)
    assert (
        expired.turns[0].status == "failed"
        and expired.turns[0].error_code == "ANSWER_LEASE_EXPIRED"
    )
    retry = await service.answer(conversation.id, body)
    assert retry.status == "succeeded"


async def test_material_sources_revalidated_and_hidden_on_revocation(context) -> None:
    service, conversation, provider, kb, file = await setup(context, "materials")
    body = AnswerRequest(request_key=uuid4(), question="PostgreSQL transaction isolation")
    answer = await service.answer(conversation.id, body)
    assert answer.citations[0].available
    async with service.sessions() as session, session.begin():
        binding = await session.get(KnowledgeBaseFile, file)
        binding.deleted_at = datetime.now(UTC)
    detail = await service.detail(conversation.id)
    assert (
        not detail.turns[0].citations[0].available and detail.turns[0].citations[0].evidence is None
    )


async def test_version_change_during_model_call_rejects_answer(context) -> None:
    service, conversation, provider, _, _ = await setup(context, "materials")

    async def changed(_):
        async with service.sessions() as session, session.begin():
            await session.execute(update(DocumentProcessingVersion).values(status="retired"))
        return GeneratedAnswer(answer="合成回答 [1]", refused=False, citation_ids=[1])

    provider.generate.side_effect = changed
    with pytest.raises(ConflictError) as error:
        await service.answer(
            conversation.id, AnswerRequest(request_key=uuid4(), question="transaction isolation")
        )
    assert error.value.error_key == "ANSWER_SOURCE_CHANGED"


async def test_no_evidence_skips_generation_and_consent_is_required(context) -> None:
    service, conversation, provider, _, _ = await setup(context, "materials")
    service.retrieval = AsyncMock()
    service.retrieval.search.return_value = RetrievalResult(
        trace_id=uuid4(), trace_complete=True, evidence=[]
    )
    result = await service.answer(
        conversation.id, AnswerRequest(request_key=uuid4(), question="无答案")
    )
    assert result.refused and not result.citations
    provider.generate.assert_not_awaited()
    settings = service.settings.model_copy(
        update={"learning_consent_version": "unconfirmed-new-version"}
    )
    other = LearningService(service.sessions, settings, service.user_id, provider=provider)
    with pytest.raises(ConflictError) as error:
        await other.answer(conversation.id, AnswerRequest(request_key=uuid4(), question="问题"))
    assert error.value.error_key == "LEARNING_CONSENT_REQUIRED"


@pytest.mark.skipif(
    not os.getenv("LEARNING_REAL_MODELS"),
    reason="explicit synthetic-only real model smoke required",
)
async def test_real_qwen_flash_general_and_material_answer(context) -> None:
    service, conversation, _, kb, _ = await setup(context)
    service.provider = QwenAnswerProvider(service.settings)
    answer = await service.answer(
        conversation.id,
        AnswerRequest(request_key=uuid4(), question="请用一句话解释数据库事务的原子性。"),
    )
    assert answer.status == "succeeded" and not answer.citations
    materials = await service.create(ConversationCreate(mode="materials", knowledge_base_id=kb))
    answer = await service.answer(
        materials.id,
        AnswerRequest(
            request_key=uuid4(), question="PostgreSQL transaction isolation prevents what?"
        ),
    )
    assert answer.status == "succeeded" and answer.citations and not answer.refused
    assert re.search(r"[\u4e00-\u9fff]", answer.answer)
