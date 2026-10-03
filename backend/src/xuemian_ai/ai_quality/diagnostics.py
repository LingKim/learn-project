"""诊断只读取当前授权来源及已记录候选，不触发线上检索或模型调用。"""

import math
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xuemian_ai.core.errors import ConflictError
from xuemian_ai.document_processing.evaluation import ranking_metrics
from xuemian_ai.document_processing.models import DocumentChunk, DocumentProcessingVersion
from xuemian_ai.file_management.models import FileAsset, KnowledgeBaseFile
from xuemian_ai.knowledge_bases.models import KnowledgeBase
from xuemian_ai.learning.result_sources import TraceCandidate, TraceMetadata

STRATEGY_VERSION = "fts-jieba-or/vector/llama-rrf/qwen-rerank-v2"
_STAGES = ("query_embedding", "keyword", "vector", "fusion", "rerank", "evidence_gate")
_MODE_STAGE = {
    "fts_only": "keyword",
    "vector_only": "vector",
    "hybrid_only": "fusion",
    "without_rerank": "fusion",
    "full": "rerank",
}


async def validate_chunks(
    session: AsyncSession, owner: UUID, knowledge_base_id: UUID, chunk_ids: list[UUID]
) -> dict[UUID, DocumentChunk]:
    """调用方须在短事务内提取授权字段；锁随该事务结束释放，不在此提交事务。"""
    # Trace 只证明历史候选，不证明此刻仍有权限。读锁阻止正文读取期间删除、
    # 移动关联或切换活动版本；重载 identity map 避免同一 Session 的历史状态。
    base = await session.scalar(
        select(KnowledgeBase)
        .where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.owner_user_id == owner,
            KnowledgeBase.deleted_at.is_(None),
        )
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if base is None:
        raise ConflictError(error_key="SOURCE_UNAVAILABLE")
    requested = set(chunk_ids)
    if not requested:
        return {}
    statement = (
        select(DocumentChunk)
        .join(
            DocumentProcessingVersion,
            DocumentProcessingVersion.id == DocumentChunk.processing_version_id,
        )
        .join(FileAsset, FileAsset.id == DocumentChunk.file_asset_id)
        .join(KnowledgeBaseFile, KnowledgeBaseFile.file_asset_id == FileAsset.id)
        .join(KnowledgeBase, KnowledgeBase.id == KnowledgeBaseFile.knowledge_base_id)
        .where(
            DocumentChunk.id.in_(requested),
            DocumentChunk.user_id == owner,
            DocumentProcessingVersion.user_id == owner,
            DocumentProcessingVersion.file_asset_id == DocumentChunk.file_asset_id,
            DocumentProcessingVersion.status == "active",
            FileAsset.owner_user_id == owner,
            FileAsset.deleted_at.is_(None),
            FileAsset.validation_status == "available",
            KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
            KnowledgeBaseFile.deleted_at.is_(None),
            KnowledgeBase.owner_user_id == owner,
            KnowledgeBase.deleted_at.is_(None),
        )
        .order_by(DocumentChunk.id)
        .with_for_update(
            read=True,
            of=(
                DocumentChunk,
                DocumentProcessingVersion,
                FileAsset,
                KnowledgeBaseFile,
                KnowledgeBase,
            ),
        )
        .execution_options(populate_existing=True)
    )
    chunks = {chunk.id: chunk for chunk in (await session.scalars(statement)).all()}
    # 整批失败，不能以部分结果悄悄缩小用户批准的来源范围。
    if set(chunks) != requested:
        raise ConflictError(error_key="SOURCE_UNAVAILABLE")
    return chunks


def _candidate_ranking(candidates: list[TraceCandidate]) -> list[TraceCandidate]:
    ordered = sorted(candidates, key=lambda candidate: candidate.rank)
    if (
        [candidate.rank for candidate in ordered] != list(range(1, len(ordered) + 1))
        or len({candidate.chunk_id for candidate in ordered}) != len(ordered)
        or any(not math.isfinite(candidate.score) for candidate in ordered)
    ):
        raise ConflictError(error_key="TRACE_INCOMPLETE")
    return ordered


def offline_replay(trace: TraceMetadata, mode: str, target_chunk_ids: list[UUID]) -> dict[str, Any]:
    """复用历史排序作只读对照；来源权限及工单授权须由调用方先独立检查。"""
    if mode not in _MODE_STAGE:
        raise ConflictError(error_key="REPLAY_MODE_INVALID")
    if trace.strategy_version != STRATEGY_VERSION:
        raise ConflictError(error_key="STRATEGY_UNAVAILABLE")
    if trace.error_code is not None or [stage.stage for stage in trace.stages] != list(_STAGES):
        raise ConflictError(error_key="TRACE_INCOMPLETE")
    stages = {stage.stage: stage for stage in trace.stages}
    rankings = {
        name: _candidate_ranking(stages[name].candidates)
        for name in ("keyword", "vector", "fusion", "rerank")
    }
    ids = {
        name: [candidate.chunk_id for candidate in ranking] for name, ranking in rankings.items()
    }
    final_ids = trace.final_chunk_ids
    if (
        not set(ids["fusion"]).issubset(set(ids["keyword"]) | set(ids["vector"]))
        or not set(ids["rerank"]).issubset(ids["fusion"])
        or len(set(final_ids)) != len(final_ids)
        or [chunk for chunk in ids["rerank"] if chunk in set(final_ids)] != final_ids
    ):
        raise ConflictError(error_key="TRACE_INCOMPLETE")
    selected = rankings[_MODE_STAGE[mode]]
    # full 保留真实门禁/top_n 之后的最终结果；其他模式没有独立门禁记录，
    # 只能展示该阶段候选，不能据此宣称重新检索或生成答案的效果。
    replay_ids = list(final_ids) if mode == "full" else [item.chunk_id for item in selected]
    metrics: dict[str, float | None] = {"recall": None, "mrr": None, "ndcg": None}
    if target_chunk_ids and all(isinstance(chunk, UUID) for chunk in target_chunk_ids):
        # 合法目标未出现在候选中仍须计为漏召回；不能丢弃后抬高 Recall。
        metrics.update(
            ranking_metrics(
                [str(chunk) for chunk in replay_ids], {str(i) for i in target_chunk_ids}
            )
        )
    return {
        "ranking": [item.model_dump() for item in selected],
        "final_chunk_ids": replay_ids,
        "metrics": metrics,
        "strategy_version": trace.strategy_version,
        "mode": mode,
        "comparison_kind": "recorded_candidates_offline",
        "independent_latency_ms": None,
        "causal_claim": False,
        "recorded_stage_metadata": [
            {
                "stage": stage.stage,
                "candidate_count": len(stage.candidates),
                "count": stage.count,
                "elapsed_ms": stage.elapsed_ms,
            }
            for stage in trace.stages
        ],
        "note": (
            "仅比较原 Trace 已记录候选；关键词为 PostgreSQL FTS/ts_rank_cd，非 BM25。"
            "Hybrid-only 与无 Rerank 在此策略中相同；非 full 模式未独立执行证据门禁。"
            "记录耗时仅引用原阶段元数据，不代表独立负载或因果实验。"
            "Recall/MRR/nDCG 使用 k=5；无合法目标标注时指标不可用。"
        ),
    }
