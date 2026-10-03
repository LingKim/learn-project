from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from xuemian_ai.accounts.models import User
from xuemian_ai.core.errors import ConflictError, NotFoundError
from xuemian_ai.document_processing.models import RetrievalTrace
from xuemian_ai.knowledge_bases.models import KnowledgeBase
from xuemian_ai.learning.models import LearningConversation, LearningTurn
from xuemian_ai.learning.result_sources import load_learning_result


class MemorySession:
    def __init__(self, objects: list[Any]) -> None:
        self.objects = {(type(obj), obj.id): obj for obj in objects}

    async def get(self, model: Any, key: Any) -> Any:
        return self.objects.get((model, key))


def source() -> tuple[AsyncSession, LearningTurn, LearningConversation, RetrievalTrace]:
    owner, kb_id, conversation_id, trace_id = uuid4(), uuid4(), uuid4(), uuid4()
    user = User(id=owner, status="active", deleted_at=None)
    base = KnowledgeBase(id=kb_id, owner_user_id=owner, deleted_at=None)
    conversation = LearningConversation(
        id=conversation_id,
        user_id=owner,
        knowledge_base_id=kb_id,
        mode="materials",
        deleted_at=None,
    )
    turn = LearningTurn(
        id=uuid4(),
        conversation_id=conversation_id,
        status="succeeded",
        answer="synthetic answer",
        question="synthetic query",
        trace_id=trace_id,
        trace_complete=True,
        citations=[],
        prompt_manifest={"agent_key": "content_analyzer", "content": "must never leak"},
        model_parameters={"temperature": 0, "key": "must never leak"},
    )
    trace = RetrievalTrace(
        id=trace_id,
        user_id=owner,
        knowledge_base_id=kb_id,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        occurred_at=datetime.now(UTC),
        strategy_version="fts",
        stages=[{"stage": "keyword", "query": "must never leak"}],
        final_chunk_ids=[],
        error_code=None,
    )
    return (
        cast(AsyncSession, MemorySession([user, base, conversation, turn, trace])),
        turn,
        conversation,
        trace,
    )


async def test_source_uses_real_relationship_and_metadata_whitelist() -> None:
    session, turn, conversation, trace = source()
    result = await load_learning_result(session, conversation.user_id, turn.id, trace.id)
    assert result.query == "synthetic query"
    assert result.identity.immutable_result_version == str(turn.id)
    assert "must never leak" not in result.trace.model_dump_json()


@pytest.mark.parametrize("change", ["owner", "trace_owner", "trace_id", "expired", "deleted"])
async def test_invalid_source_cannot_authorize_content(change: str) -> None:
    session, turn, conversation, trace = source()
    owner = conversation.user_id
    if change == "owner":
        owner = uuid4()
    elif change == "trace_owner":
        trace.user_id = uuid4()
    elif change == "trace_id":
        turn.trace_id = uuid4()
    elif change == "expired":
        trace.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    else:
        conversation.deleted_at = datetime.now(UTC)
    with pytest.raises(NotFoundError):
        await load_learning_result(session, owner, turn.id, trace.id)


async def test_general_and_incomplete_turn_reject_feedback_source() -> None:
    session, turn, conversation, trace = source()
    turn.trace_complete = False
    with pytest.raises(ConflictError) as error:
        await load_learning_result(session, conversation.user_id, turn.id, trace.id)
    assert error.value.error_key == "TRACE_INCOMPLETE"
    conversation.mode = "general"
    with pytest.raises(ConflictError) as error:
        await load_learning_result(session, conversation.user_id, turn.id, trace.id)
    assert error.value.error_key == "SOURCE_UNAVAILABLE"
