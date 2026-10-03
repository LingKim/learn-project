"""质量工单的领域读取边界：不能仅凭 Trace ID 取得用户正文。"""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from xuemian_ai.accounts.models import User
from xuemian_ai.core.errors import ConflictError, NotFoundError
from xuemian_ai.document_processing.models import RetrievalTrace
from xuemian_ai.knowledge_bases.models import KnowledgeBase
from xuemian_ai.learning.models import LearningConversation, LearningTurn


class ResultIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_type: Literal["learning_turn"] = "learning_turn"
    source_id: UUID
    owner_user_id: UUID
    immutable_result_version: str
    trace_ids: list[UUID]
    prompt_run_id: UUID | None = None


class TraceCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_id: UUID
    rank: int
    score: float


class TraceStageMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage: str
    elapsed_ms: int | None = None
    candidates: list[TraceCandidate] = Field(default_factory=list)
    count: int | None = None


class TraceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trace_id: UUID
    strategy_version: str
    stages: list[TraceStageMetadata]
    final_chunk_ids: list[UUID]
    occurred_at: datetime
    expires_at: datetime
    error_code: str | None
    prompt_manifest: dict[str, Any]
    model_parameters: dict[str, Any]


class LearningResultSource(BaseModel):
    """仅授予加密快照构造器；禁止把此模型用于管理员详情响应。"""

    model_config = ConfigDict(extra="forbid")
    identity: ResultIdentity
    knowledge_base_id: UUID
    query: str
    final_output: str
    final_citations: list[dict[str, str | int]]
    trace: TraceMetadata


async def load_learning_result(
    session: AsyncSession, owner_user_id: UUID, source_id: UUID, trace_id: UUID
) -> LearningResultSource:
    owner = await session.get(User, owner_user_id)
    if owner is None or owner.deleted_at is not None or owner.status != "active":
        raise NotFoundError(error_key="SOURCE_UNAVAILABLE")
    turn = await session.get(LearningTurn, source_id)
    conversation = await session.get(LearningConversation, turn.conversation_id) if turn else None
    if (
        turn is None
        or conversation is None
        or conversation.user_id != owner_user_id
        or conversation.deleted_at is not None
    ):
        raise NotFoundError(error_key="SOURCE_UNAVAILABLE")
    if conversation.mode != "materials" or turn.status != "succeeded" or turn.answer is None:
        raise ConflictError(error_key="SOURCE_UNAVAILABLE")
    if not turn.trace_complete or turn.trace_id is None:
        raise ConflictError(error_key="TRACE_INCOMPLETE")
    if turn.trace_id != trace_id:
        raise NotFoundError(error_key="TRACE_UNAVAILABLE")
    base = await session.get(KnowledgeBase, conversation.knowledge_base_id)
    if base is None or base.owner_user_id != owner_user_id or base.deleted_at is not None:
        raise ConflictError(error_key="SOURCE_UNAVAILABLE")
    trace = await session.get(RetrievalTrace, trace_id)
    if (
        trace is None
        or trace.user_id != owner_user_id
        or trace.knowledge_base_id != base.id
        or trace.expires_at <= datetime.now(UTC)
    ):
        raise NotFoundError(error_key="TRACE_UNAVAILABLE")
    stages = []
    # 只选非正文元数据，不把原始 JSON 扩散到管理员 API。
    for item in trace.stages:
        candidates = item.get("candidates", [])
        elapsed = item.get("elapsed_ms")
        count = item.get("count")
        stages.append(
            TraceStageMetadata(
                stage=str(item.get("stage", "unknown")),
                elapsed_ms=elapsed if isinstance(elapsed, int) else None,
                count=count if isinstance(count, int) else None,
                candidates=[TraceCandidate.model_validate(c) for c in candidates]
                if isinstance(candidates, list)
                else [],
            )
        )
    return LearningResultSource(
        identity=ResultIdentity(
            source_id=turn.id,
            owner_user_id=owner_user_id,
            immutable_result_version=str(turn.id),
            trace_ids=[trace.id],
        ),
        knowledge_base_id=base.id,
        query=turn.question,
        final_output=turn.answer,
        final_citations=turn.citations,
        trace=TraceMetadata(
            trace_id=trace.id,
            strategy_version=trace.strategy_version,
            stages=stages,
            final_chunk_ids=[UUID(i) for i in trace.final_chunk_ids],
            occurred_at=trace.occurred_at,
            expires_at=trace.expires_at,
            error_code=trace.error_code,
            prompt_manifest={
                key: value
                for key, value in turn.prompt_manifest.items()
                if key in {"agent_key", "scene_key", "input_schema", "output_schema", "sha256"}
                and isinstance(value, str)
            },
            model_parameters={
                key: value
                for key, value in turn.model_parameters.items()
                if key in {"model", "temperature", "enable_thinking"}
                and isinstance(value, str | int | float | bool)
            },
        ),
    )
