from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from xuemian_ai.ai_quality.diagnostics import STRATEGY_VERSION, offline_replay, validate_chunks
from xuemian_ai.core.errors import ConflictError
from xuemian_ai.document_processing.models import DocumentChunk
from xuemian_ai.knowledge_bases.models import KnowledgeBase
from xuemian_ai.learning.result_sources import TraceCandidate, TraceMetadata, TraceStageMetadata


def trace_fixture() -> tuple[TraceMetadata, list[UUID]]:
    ids = [uuid4() for _ in range(3)]
    orders = {
        "keyword": [ids[0], ids[1]],
        "vector": [ids[2], ids[0]],
        "fusion": [ids[0], ids[2], ids[1]],
        "rerank": [ids[2], ids[1], ids[0]],
    }
    stages = [TraceStageMetadata(stage="query_embedding", elapsed_ms=10)]
    for name, chunks in orders.items():
        stages.append(
            TraceStageMetadata(
                stage=name,
                elapsed_ms=20,
                candidates=[
                    TraceCandidate(chunk_id=chunk, rank=index + 1, score=1 - index * 0.2)
                    for index, chunk in enumerate(chunks)
                ],
            )
        )
    stages.append(TraceStageMetadata(stage="evidence_gate"))
    now = datetime.now(UTC)
    return (
        TraceMetadata(
            trace_id=uuid4(),
            strategy_version=STRATEGY_VERSION,
            stages=stages,
            final_chunk_ids=[ids[2], ids[1]],
            occurred_at=now,
            expires_at=now + timedelta(days=1),
            error_code=None,
            prompt_manifest={},
            model_parameters={},
        ),
        ids,
    )


@pytest.mark.parametrize(
    ("mode", "indices", "mrr"),
    [
        ("fts_only", [0, 1], 0.0),
        ("vector_only", [2, 0], 1.0),
        ("hybrid_only", [0, 2, 1], 0.5),
        ("without_rerank", [0, 2, 1], 0.5),
        ("full", [2, 1], 1.0),
    ],
)
def test_offline_modes_use_recorded_order_and_real_final_gate(
    mode: str, indices: list[int], mrr: float
) -> None:
    trace, ids = trace_fixture()
    # 序列化顺序不是排名；必须按记录的 rank 恢复。
    for stage in trace.stages:
        stage.candidates.reverse()
    result = offline_replay(trace, mode, [ids[2]])
    assert result["final_chunk_ids"] == [ids[index] for index in indices]
    assert result["metrics"]["mrr"] == mrr
    expected_ranking = [2, 1, 0] if mode == "full" else indices
    assert [item["chunk_id"] for item in result["ranking"]] == [ids[i] for i in expected_ranking]
    assert result["strategy_version"] == STRATEGY_VERSION
    assert result["mode"] == mode
    assert result["comparison_kind"] == "recorded_candidates_offline"
    assert result["causal_claim"] is False
    assert result["independent_latency_ms"] is None
    assert result["recorded_stage_metadata"][0]["elapsed_ms"] == 10
    assert result["recorded_stage_metadata"][-1]["elapsed_ms"] is None
    assert "非 BM25" in result["note"]


def test_hybrid_and_without_rerank_share_the_same_recorded_candidates() -> None:
    trace, ids = trace_fixture()
    hybrid = offline_replay(trace, "hybrid_only", [ids[2]])
    no_rerank = offline_replay(trace, "without_rerank", [ids[2]])
    for key in ("ranking", "final_chunk_ids", "metrics"):
        assert hybrid[key] == no_rerank[key]


def test_metrics_require_targets_but_count_unretrieved_targets_and_duplicates() -> None:
    trace, ids = trace_fixture()
    unavailable = {"recall": None, "mrr": None, "ndcg": None}
    assert offline_replay(trace, "full", [])["metrics"] == unavailable
    assert offline_replay(trace, "full", cast(list[UUID], ["bad"]))["metrics"] == unavailable
    assert offline_replay(trace, "full", [uuid4()])["metrics"] == {
        "recall": 0.0,
        "mrr": 0.0,
        "ndcg": 0.0,
    }
    assert offline_replay(trace, "full", [ids[2], ids[2]])["metrics"] == {
        "recall": 1.0,
        "mrr": 1.0,
        "ndcg": 1.0,
    }
    assert offline_replay(trace, "full", [ids[2], uuid4()])["metrics"]["recall"] == 0.5
    # 原门禁删除的候选不能计为完整策略命中。
    assert offline_replay(trace, "full", [ids[0]])["metrics"]["recall"] == 0.0


def test_empty_recorded_stages_are_valid_and_keep_metrics_meaningful() -> None:
    trace, _ = trace_fixture()
    for stage in trace.stages:
        stage.candidates = []
    trace.final_chunk_ids = []
    result = offline_replay(trace, "full", [uuid4()])
    assert result["ranking"] == result["final_chunk_ids"] == []
    assert result["metrics"]["recall"] == 0.0


def test_metrics_apply_top_five_cutoff_and_do_not_mutate_the_original_trace() -> None:
    trace, _ = trace_fixture()
    ids = [uuid4() for _ in range(6)]
    for stage in trace.stages[1:5]:
        stage.candidates = [
            TraceCandidate(chunk_id=chunk, rank=index + 1, score=1 - index * 0.1)
            for index, chunk in enumerate(ids)
        ]
    trace.final_chunk_ids = ids
    original = trace.model_dump()
    result = offline_replay(trace, "full", [ids[-1]])
    assert result["final_chunk_ids"] == ids
    assert result["metrics"] == {"recall": 0.0, "mrr": 0.0, "ndcg": 0.0}
    result = offline_replay(trace, "full", ids)
    assert result["metrics"]["recall"] == 5 / 6
    assert result["metrics"]["ndcg"] == 1.0
    assert trace.model_dump() == original


@pytest.mark.parametrize(
    "mode,version,key",
    [
        ("bm25_only", STRATEGY_VERSION, "REPLAY_MODE_INVALID"),
        ("full", "old-strategy", "STRATEGY_UNAVAILABLE"),
    ],
)
def test_replay_rejects_modes_or_strategies_it_cannot_reproduce(
    mode: str, version: str, key: str
) -> None:
    trace, _ = trace_fixture()
    trace.strategy_version = version
    with pytest.raises(ConflictError) as error:
        offline_replay(trace, mode, [])
    assert error.value.error_key == key


@pytest.mark.parametrize(
    "change",
    [
        "missing_stage",
        "duplicate_stage",
        "stage_order",
        "trace_error",
        "rank_gap",
        "duplicate_chunk",
        "nan_score",
        "infinity_score",
        "foreign_fusion",
        "foreign_rerank",
        "foreign_final",
        "duplicate_final",
        "reordered_final",
    ],
)
def test_incomplete_or_inconsistent_trace_is_explicitly_rejected(change: str) -> None:
    trace, ids = trace_fixture()
    if change == "missing_stage":
        trace.stages.pop()
    elif change == "duplicate_stage":
        trace.stages.append(trace.stages[1])
    elif change == "stage_order":
        trace.stages.reverse()
    elif change == "trace_error":
        trace.error_code = "PROVIDER_FAILED"
    elif change == "rank_gap":
        trace.stages[1].candidates[0].rank = 10
    elif change == "duplicate_chunk":
        trace.stages[1].candidates[0].chunk_id = ids[1]
    elif change in {"nan_score", "infinity_score"}:
        trace.stages[1].candidates[0].score = float("nan" if change == "nan_score" else "inf")
    elif change == "foreign_fusion":
        trace.stages[3].candidates[0].chunk_id = uuid4()
    elif change == "foreign_rerank":
        trace.stages[4].candidates[0].chunk_id = uuid4()
    elif change == "foreign_final":
        trace.final_chunk_ids = [uuid4()]
    elif change == "duplicate_final":
        trace.final_chunk_ids.append(ids[2])
    else:
        trace.final_chunk_ids.reverse()
    with pytest.raises(ConflictError) as error:
        offline_replay(trace, "full", [])
    assert error.value.error_key == "TRACE_INCOMPLETE"


class ReadSession:
    def __init__(self, base: KnowledgeBase | None, chunks: list[DocumentChunk]) -> None:
        self.base, self.chunks = base, chunks
        self.statements: list[Any] = []

    async def scalar(self, statement: Any) -> KnowledgeBase | None:
        self.statements.append(statement)
        return self.base

    async def scalars(self, statement: Any) -> "ReadSession":
        self.statements.append(statement)
        return self

    def all(self) -> list[DocumentChunk]:
        return self.chunks


async def test_validate_chunks_locks_every_source_table_and_reloads_current_state() -> None:
    owner, kb, chunk_id = uuid4(), uuid4(), uuid4()
    chunk = DocumentChunk(id=chunk_id)
    session = ReadSession(KnowledgeBase(id=kb), [chunk])
    result = await validate_chunks(cast(AsyncSession, session), owner, kb, [chunk_id, chunk_id])
    assert result == {chunk_id: chunk}
    statement = session.statements[1]
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert (
        "FOR SHARE OF document_chunks, document_processing_versions, file_assets, "
        "knowledge_base_files, knowledge_bases" in sql
    )
    for condition in (
        "document_processing_versions.file_asset_id = document_chunks.file_asset_id",
        "document_processing_versions.status =",
        "document_chunks.user_id =",
        "document_processing_versions.user_id =",
        "file_assets.owner_user_id =",
        "file_assets.validation_status =",
        "file_assets.deleted_at IS NULL",
        "knowledge_base_files.knowledge_base_id =",
        "knowledge_base_files.deleted_at IS NULL",
        "knowledge_bases.owner_user_id =",
        "knowledge_bases.deleted_at IS NULL",
    ):
        assert condition in sql
    assert "active" in compiled.params.values()
    assert "available" in compiled.params.values()
    assert kb in compiled.params.values()
    assert owner in compiled.params.values()
    assert all(stmt.get_execution_options()["populate_existing"] for stmt in session.statements)


@pytest.mark.parametrize("available", ["no_base", "no_chunk", "partial", "extra"])
async def test_validate_chunks_fails_the_entire_batch_when_any_id_is_unavailable(
    available: str,
) -> None:
    owner, kb = uuid4(), uuid4()
    chunks = [DocumentChunk(id=uuid4()), DocumentChunk(id=uuid4())]
    requested = [chunk.id for chunk in chunks]
    returned = [] if available == "no_chunk" else chunks[:1]
    if available == "extra":
        returned = [*chunks, DocumentChunk(id=uuid4())]
    session = ReadSession(None if available == "no_base" else KnowledgeBase(id=kb), returned)
    with pytest.raises(ConflictError) as error:
        await validate_chunks(cast(AsyncSession, session), owner, kb, requested)
    assert error.value.error_key == "SOURCE_UNAVAILABLE"


async def test_empty_chunk_list_still_validates_the_knowledge_base() -> None:
    session = ReadSession(KnowledgeBase(id=uuid4()), [])
    assert await validate_chunks(cast(AsyncSession, session), uuid4(), session.base.id, []) == {}
    assert len(session.statements) == 1
    session.base = None
    with pytest.raises(ConflictError):
        await validate_chunks(cast(AsyncSession, session), uuid4(), uuid4(), [])
