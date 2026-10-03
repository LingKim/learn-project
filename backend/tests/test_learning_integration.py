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


async def test_no_evidence_skips_generation_without_learning_consent(context) -> None:
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
    result = await other.answer(
        conversation.id, AnswerRequest(request_key=uuid4(), question="问题")
    )
    assert result.status == "succeeded"


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


async def test_stream_progress_is_not_persisted_and_success_replay_uses_profile_language(context):
    from types import SimpleNamespace

    from xuemian_ai.profiles.models import UserProfile

    service, conversation, _, _, _ = await setup(context)
    async with service.sessions() as session, session.begin():
        session.add(UserProfile(user_id=service.user_id, preferred_language="en-US"))

    async def streaming(context):
        assert context.answer_language == "en"
        yield "Partial "
        async with service.sessions() as session:
            turn = await session.scalar(
                select(LearningTurn).where(LearningTurn.conversation_id == conversation.id)
            )
            assert turn.status == "processing" and turn.answer is None
        yield "answer"
        yield GeneratedAnswer(answer="Partial answer", refused=False, citation_ids=[])

    service.provider = SimpleNamespace(stream=streaming)
    body = AnswerRequest(request_key=uuid4(), question="Synthetic question")
    events = [
        event
        async for event in service.stream_answer(
            await service.prepare_answer(conversation.id, body)
        )
    ]
    assert [event.type for event in events] == ["started", "delta", "delta", "completed"]
    assert events[-1].turn.answer == "Partial answer"
    async with service.sessions() as session, session.begin():
        await session.execute(
            update(UserProfile)
            .where(UserProfile.user_id == service.user_id)
            .values(preferred_language="zh-CN")
        )
    replay = [
        event
        async for event in service.stream_answer(
            await service.prepare_answer(conversation.id, body)
        )
    ]
    assert [event.type for event in replay] == ["started", "completed"]
    assert replay[-1].turn.language == "en" and replay[-1].turn.id == events[-1].turn.id
    stranger = LearningService(service.sessions, service.settings, uuid4())
    with pytest.raises(NotFoundError):
        await stranger.prepare_answer(conversation.id, body)


@pytest.mark.parametrize(
    "final,error_key",
    [
        (
            GeneratedAnswer(answer="无效回答 [99]", refused=False, citation_ids=[99]),
            "ANSWER_CITATION_INVALID",
        ),
        (
            GeneratedAnswer(
                answer="说明：### 1. 用法```javascriptimport { watch } from 'vue';```",
                refused=False,
                citation_ids=[],
            ),
            "ANSWER_MARKDOWN_INVALID",
        ),
    ],
)
async def test_stream_invalid_final_does_not_publish_partial_and_retries_same_turn(
    context, final, error_key
):
    from types import SimpleNamespace

    service, conversation, _, _, _ = await setup(context)

    async def invalid(_):
        yield "未校验正文"
        yield final

    service.provider = SimpleNamespace(stream=invalid)
    body = AnswerRequest(request_key=uuid4(), question="问题")
    prepared = await service.prepare_answer(conversation.id, body)
    events = [event async for event in service.stream_answer(prepared)]
    assert [event.type for event in events] == ["started", "delta", "failed"]
    assert events[-1].error_code == error_key
    detail = await service.detail(conversation.id)
    assert detail.turns[0].status == "failed" and detail.turns[0].answer is None

    async def valid(_):
        yield "已校验"
        yield GeneratedAnswer(answer="已校验", refused=False, citation_ids=[])

    service.provider = SimpleNamespace(stream=valid)
    retry = [
        event
        async for event in service.stream_answer(
            await service.prepare_answer(conversation.id, body)
        )
    ]
    assert retry[-1].turn.status == "succeeded" and retry[-1].turn.id == prepared.turn_id
    assert len((await service.detail(conversation.id)).turns) == 1


async def test_stream_disconnect_closes_upstream_and_releases_owned_lease(context):
    from types import SimpleNamespace

    service, conversation, _, _, _ = await setup(context)
    closed = asyncio.Event()

    async def blocked(_):
        try:
            yield "临时"
            await asyncio.Event().wait()
        finally:
            closed.set()

    service.provider = SimpleNamespace(stream=blocked)
    body = AnswerRequest(request_key=uuid4(), question="问题")
    stream = service.stream_answer(await service.prepare_answer(conversation.id, body))
    assert (await anext(stream)).type == "started"
    assert (await anext(stream)).type == "delta"
    await stream.aclose()
    assert closed.is_set()
    detail = await service.detail(conversation.id)
    assert detail.turns[0].status == "failed"
    assert detail.turns[0].answer is None and detail.turns[0].error_code == "ANSWER_CANCELLED"
    assert (await service.prepare_answer(conversation.id, body)).turn_id == detail.turns[0].id


async def test_stream_revoked_source_after_delta_is_not_published(context):
    from types import SimpleNamespace

    service, conversation, _, _, file = await setup(context, "materials")

    async def revoked(_):
        yield "资料回答 [1]"
        async with service.sessions() as session, session.begin():
            binding = await session.get(KnowledgeBaseFile, file)
            binding.deleted_at = datetime.now(UTC)
        yield "撤权后必须不发送"
        yield GeneratedAnswer(answer="资料回答 [1]", refused=False, citation_ids=[1])

    service.provider = SimpleNamespace(stream=revoked)
    prepared = await service.prepare_answer(
        conversation.id, AnswerRequest(request_key=uuid4(), question="transaction isolation")
    )
    events = [event async for event in service.stream_answer(prepared)]
    assert [event.delta for event in events if event.type == "delta"] == ["资料回答 [1]"]
    assert events[-1].type == "failed" and events[-1].error_code in {
        "ANSWER_SOURCE_CHANGED",
        "KNOWLEDGE_FILE_NOT_FOUND",
    }
    assert (await service.detail(conversation.id)).turns[0].answer is None


async def test_stream_task_cancellation_closes_provider_and_marks_failure(context):
    from types import SimpleNamespace

    service, conversation, _, _, _ = await setup(context)
    entered, closed = asyncio.Event(), asyncio.Event()

    async def blocked(_):
        try:
            entered.set()
            await asyncio.Event().wait()
            yield "unreachable"
        finally:
            closed.set()

    service.provider = SimpleNamespace(stream=blocked)
    prepared = await service.prepare_answer(
        conversation.id, AnswerRequest(request_key=uuid4(), question="问题")
    )

    async def consume():
        return [event async for event in service.stream_answer(prepared)]

    task = asyncio.create_task(consume())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()
    turn = (await service.detail(conversation.id)).turns[0]
    assert turn.status == "failed" and turn.answer is None and turn.error_code == "ANSWER_CANCELLED"


async def test_stream_deactivated_user_stops_before_next_delta(context):
    from types import SimpleNamespace

    from xuemian_ai.accounts.models import User

    service, conversation, _, _, _ = await setup(context)

    async def changed(_):
        yield "授权时正文"
        async with service.sessions() as session, session.begin():
            await session.execute(
                update(User).where(User.id == service.user_id).values(deleted_at=datetime.now(UTC))
            )
        yield "撤权后正文"
        yield GeneratedAnswer(answer="完整正文", refused=False, citation_ids=[])

    service.provider = SimpleNamespace(stream=changed)
    prepared = await service.prepare_answer(
        conversation.id, AnswerRequest(request_key=uuid4(), question="问题")
    )
    events = [event async for event in service.stream_answer(prepared)]
    assert [event.delta for event in events if event.type == "delta"] == ["授权时正文"]
    assert events[-1].type == "failed" and events[-1].error_code == "USER_NOT_FOUND"
    async with service.sessions() as session:
        turn = await session.get(LearningTurn, prepared.turn_id)
        assert turn.status == "failed" and turn.answer is None


async def test_replay_rechecks_deleted_conversation_before_emitting(context):
    service, conversation, _, _, _ = await setup(context)
    body = AnswerRequest(request_key=uuid4(), question="问题")
    await service.answer(conversation.id, body)
    prepared = await service.prepare_answer(conversation.id, body)
    await service.delete(conversation.id)
    events = [event async for event in service.stream_answer(prepared)]
    assert [event.type for event in events] == ["failed"]
    assert events[0].error_code == "LEARNING_CONVERSATION_NOT_FOUND"
    assert events[0].turn is None


async def test_replay_refreshes_revoked_citations_before_emitting(context):
    service, conversation, _, _, file = await setup(context, "materials")
    body = AnswerRequest(request_key=uuid4(), question="transaction isolation")
    answer = await service.answer(conversation.id, body)
    assert answer.citations[0].available
    prepared = await service.prepare_answer(conversation.id, body)
    async with service.sessions() as session, session.begin():
        binding = await session.get(KnowledgeBaseFile, file)
        binding.deleted_at = datetime.now(UTC)
    events = [event async for event in service.stream_answer(prepared)]
    assert [event.type for event in events] == ["started", "completed"]
    assert not events[0].turn.citations[0].available
    assert events[0].turn.citations[0].evidence is None


async def test_response_cleanup_releases_lease_without_starting_iterator(context):
    from xuemian_ai.api.learning import AnswerEventResponse

    service, conversation, _, _, _ = await setup(context)
    body = AnswerRequest(request_key=uuid4(), question="问题")
    prepared = await service.prepare_answer(conversation.id, body)
    entered = False

    async def untouched():
        nonlocal entered
        entered = True
        yield "unreachable"

    stream = untouched()
    await stream.aclose()
    response = AnswerEventResponse(stream, service, prepared)

    async def disconnect():
        return {"type": "http.disconnect"}

    async def broken_send(_message):
        raise RuntimeError("synthetic disconnected response")

    with pytest.raises(RuntimeError):
        await response({"type": "http", "asgi": {"spec_version": "2.4"}}, disconnect, broken_send)
    assert not entered
    detail = await service.detail(conversation.id)
    assert detail.turns[0].status == "failed" and detail.turns[0].error_code == "ANSWER_CANCELLED"
    newer = await service.prepare_answer(conversation.id, body)
    await service.cancel_prepared(prepared)
    assert (await service.detail(conversation.id)).turns[0].status == "processing"
    await service.cancel_prepared(newer)
