import hashlib
import hmac
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from llama_index.core.llms import MockLLM
from llama_index.core.retrievers import BaseRetriever, QueryFusionRetriever
from llama_index.core.retrievers.fusion_retriever import FUSION_MODES
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from xuemian_ai.core.config import Settings
from xuemian_ai.core.errors import ConflictError, NotFoundError, UpstreamServiceError
from xuemian_ai.core.logging import get_logger
from xuemian_ai.document_processing.models import (
    DocumentChunk,
    DocumentProcessingVersion,
    RetrievalTrace,
    VectorIndexProfile,
)
from xuemian_ai.document_processing.parsers import ProcessingError
from xuemian_ai.document_processing.providers import model_providers
from xuemian_ai.document_processing.schemas import EvidenceChunk, RetrievalRequest, RetrievalResult
from xuemian_ai.document_processing.service import has_consent
from xuemian_ai.document_processing.tokenization import keyword_query
from xuemian_ai.document_processing.vector_store import VectorStore
from xuemian_ai.file_management.models import FileAsset, KnowledgeBaseFile
from xuemian_ai.knowledge_bases.models import KnowledgeBase

_logger = get_logger(__name__)


class AuthorizedCandidateRetriever(BaseRetriever):
    def __init__(self, candidates: list[tuple[UUID, float]]) -> None:
        super().__init__()
        self.candidates = candidates

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        # 融合只携带已授权 ID，不向框架交付正文或秘密。
        return [
            NodeWithScore(
                node=TextNode(id_=str(chunk), text="", metadata={"chunk_id": str(chunk)}),
                score=score,
            )
            for chunk, score in self.candidates
        ]


def fuse_candidates(
    keyword: list[tuple[UUID, float]], vector: list[tuple[UUID, float]], limit: int
) -> list[tuple[UUID, float]]:
    fusion = QueryFusionRetriever(
        [AuthorizedCandidateRetriever(keyword), AuthorizedCandidateRetriever(vector)],
        llm=MockLLM(),
        mode=FUSION_MODES.RECIPROCAL_RANK,
        similarity_top_k=limit,
        num_queries=1,
        use_async=False,
    )
    return [
        (UUID(item.node.node_id), item.score or 0)
        for item in fusion.retrieve(QueryBundle("authorized-candidates"))
    ]


class RetrievalService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
        user_id: UUID,
        request_id: str | None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self.sessions, self.settings, self.user_id, self.request_id = (
            sessions,
            settings,
            user_id,
            request_id,
        )
        self.vector_store = vector_store or VectorStore(settings)
        self.owns_store = vector_store is None
        self.embedding, self.rerank = model_providers(settings)

    def authorized_chunks(
        self, kb: UUID, files: list[UUID]
    ) -> Select[tuple[DocumentChunk, KnowledgeBaseFile]]:
        statement = (
            select(DocumentChunk, KnowledgeBaseFile)
            .join(
                DocumentProcessingVersion,
                DocumentProcessingVersion.id == DocumentChunk.processing_version_id,
            )
            .join(FileAsset, FileAsset.id == DocumentChunk.file_asset_id)
            .join(KnowledgeBaseFile, KnowledgeBaseFile.file_asset_id == FileAsset.id)
            .join(KnowledgeBase, KnowledgeBase.id == KnowledgeBaseFile.knowledge_base_id)
            .where(
                DocumentChunk.user_id == self.user_id,
                DocumentProcessingVersion.user_id == self.user_id,
                DocumentProcessingVersion.status == "active",
                FileAsset.owner_user_id == self.user_id,
                FileAsset.deleted_at.is_(None),
                KnowledgeBaseFile.deleted_at.is_(None),
                KnowledgeBase.id == kb,
                KnowledgeBase.owner_user_id == self.user_id,
                KnowledgeBase.deleted_at.is_(None),
            )
        )
        if files:
            statement = statement.where(KnowledgeBaseFile.id.in_(files))
        return statement

    async def trace(
        self,
        trace_id: UUID,
        kb: UUID,
        query: str,
        stages: list[dict[str, object]],
        final_ids: list[str],
        code: str | None,
    ) -> bool:
        now = datetime.now(UTC)
        try:
            async with self.sessions() as session, session.begin():
                session.add(
                    RetrievalTrace(
                        id=trace_id,
                        user_id=self.user_id,
                        knowledge_base_id=kb,
                        request_id=self.request_id,
                        query_digest=hmac.new(
                            self.settings.auth_fingerprint_secret.get_secret_value().encode(),
                            query.encode(),
                            hashlib.sha256,
                        ).hexdigest(),
                        query_length=len(query),
                        strategy_version="fts-jieba-or/vector/llama-rrf/qwen-rerank-v2",
                        stages=stages,
                        final_chunk_ids=final_ids,
                        error_code=code,
                        occurred_at=now,
                        expires_at=now + timedelta(days=30),
                        retained_by_case=False,
                    )
                )
            return True
        except Exception:
            _logger.error("retrieval_trace_write_failed", error_key="RETRIEVAL_TRACE_INCOMPLETE")
            return False

    async def search(self, kb: UUID, request: RetrievalRequest) -> RetrievalResult:
        try:
            return await self._search(kb, request)
        finally:
            if self.owns_store:
                await self.vector_store.close()

    async def _search(self, kb: UUID, request: RetrievalRequest) -> RetrievalResult:
        trace_id = uuid4()
        stages: list[dict[str, object]] = []
        async with self.sessions() as session:
            base = await session.scalar(
                select(KnowledgeBase.id).where(
                    KnowledgeBase.id == kb,
                    KnowledgeBase.owner_user_id == self.user_id,
                    KnowledgeBase.deleted_at.is_(None),
                )
            )
            if base is None:
                raise NotFoundError(error_key="KNOWLEDGE_BASE_NOT_FOUND")
            if not await has_consent(session, self.user_id, self.settings):
                raise ConflictError(
                    "请先确认 AI 资料处理说明", error_key="AI_PROCESSING_CONSENT_REQUIRED"
                )
            if request.file_ids:
                allowed = (
                    await session.scalars(
                        select(KnowledgeBaseFile.id)
                        .join(FileAsset, FileAsset.id == KnowledgeBaseFile.file_asset_id)
                        .where(
                            KnowledgeBaseFile.knowledge_base_id == kb,
                            KnowledgeBaseFile.id.in_(request.file_ids),
                            KnowledgeBaseFile.deleted_at.is_(None),
                            FileAsset.owner_user_id == self.user_id,
                            FileAsset.deleted_at.is_(None),
                        )
                    )
                ).all()
                if set(allowed) != set(request.file_ids):
                    raise NotFoundError(error_key="KNOWLEDGE_FILE_NOT_FOUND")
            versions = (
                await session.scalars(
                    self.authorized_chunks(kb, request.file_ids)
                    .with_only_columns(DocumentChunk.processing_version_id)
                    .distinct()
                )
            ).all()
            profiles = (
                await session.scalars(
                    select(VectorIndexProfile)
                    .join(
                        DocumentProcessingVersion,
                        DocumentProcessingVersion.profile_id == VectorIndexProfile.id,
                    )
                    .where(DocumentProcessingVersion.id.in_(versions))
                    .distinct()
                )
            ).all()
            if any(
                p.provider != self.settings.document_provider
                or p.model != self.settings.document_embedding_model
                or p.collection != self.settings.qdrant_collection
                or p.dimensions != 1024
                for p in profiles
            ):
                raise ConflictError(
                    "当前索引与检索配置不兼容，请重新解析",
                    error_key="DOCUMENT_PROFILE_INCOMPATIBLE",
                )
        try:
            if not versions:
                complete = await self.trace(trace_id, kb, request.query, stages, [], None)
                return RetrievalResult(trace_id=trace_id, trace_complete=complete, evidence=[])
            limit = self.settings.document_retrieval_candidates
            start = time.monotonic()
            await self.vector_store.check_schema()
            vector = (await self.embedding.embed([request.query]))[0]
            stages.append(
                {
                    "stage": "query_embedding",
                    "elapsed_ms": round((time.monotonic() - start) * 1000),
                    "model": self.settings.document_embedding_model,
                    "versions": [str(v) for v in versions],
                }
            )
            start = time.monotonic()
            async with self.sessions() as session:
                query = func.websearch_to_tsquery("simple", keyword_query(request.query))
                keyword_score = func.ts_rank_cd(DocumentChunk.search_vector, query).label("score")
                rows = (
                    await session.execute(
                        self.authorized_chunks(kb, request.file_ids)
                        .with_only_columns(DocumentChunk.id, keyword_score)
                        .where(DocumentChunk.search_vector.op("@@")(query))
                        .order_by(keyword_score.desc(), DocumentChunk.id)
                        .limit(limit)
                    )
                ).all()
                keyword = [(row[0], float(row[1])) for row in rows]
            stages.append(self.event("keyword", keyword, start))
            start = time.monotonic()
            vectors = await self.vector_store.search(self.user_id, versions, vector, limit)
            stages.append(self.event("vector", vectors, start))
            start = time.monotonic()
            # 两路候选都重新在 PostgreSQL 复核后才交给 LlamaIndex。
            async with self.sessions() as session:
                ids = [item[0] for item in keyword + vectors]
                allowed_chunks = set(
                    (
                        await session.scalars(
                            self.authorized_chunks(kb, request.file_ids)
                            .with_only_columns(DocumentChunk.id)
                            .where(DocumentChunk.id.in_(ids))
                        )
                    ).all()
                )
            keyword = [item for item in keyword if item[0] in allowed_chunks]
            vectors = [item for item in vectors if item[0] in allowed_chunks]
            fused = fuse_candidates(keyword, vectors, limit)
            stages.append(self.event("fusion", fused, start))
            async with self.sessions() as session:
                chunks = {
                    row[0].id: row[0]
                    for row in (
                        await session.execute(
                            self.authorized_chunks(kb, request.file_ids).where(
                                DocumentChunk.id.in_([item[0] for item in fused])
                            )
                        )
                    ).all()
                }
            fused = [item for item in fused if item[0] in chunks]
            start = time.monotonic()
            ranked = await self.rerank.rerank(
                request.query, [chunks[item[0]].content for item in fused]
            )
            ranking = [(fused[index][0], score) for index, score in ranked]
            stages.append(self.event("rerank", ranking, start))
            ranking = [
                item for item in ranking if item[1] >= self.settings.document_retrieval_min_score
            ]
            stages.append(
                {
                    "stage": "evidence_gate",
                    "minimum_score": self.settings.document_retrieval_min_score,
                    "accepted_count": len(ranking),
                }
            )
            final_ids = [chunk_id for chunk_id, _ in ranking]
            # 返回前再验证当前关联和活动版本；删除/移动/版本切换后丢弃失效候选。
            async with self.sessions() as session:
                rows = (
                    await session.execute(
                        self.authorized_chunks(kb, request.file_ids).where(
                            DocumentChunk.id.in_(final_ids)
                        )
                    )
                ).all()
                final = {chunk.id: (chunk, binding) for chunk, binding in rows}
            evidence: list[EvidenceChunk] = []
            for chunk_id, score in ranking:
                if chunk_id not in final:
                    continue
                if len(evidence) >= request.top_n:
                    break
                chunk, binding = final[chunk_id]
                evidence.append(
                    EvidenceChunk(
                        chunk_id=chunk.id,
                        file_id=binding.id,
                        file_name=binding.display_name,
                        processing_version_id=chunk.processing_version_id,
                        content=chunk.content,
                        score=score,
                        source_kind=chunk.source_kind,
                        page_start=chunk.page_start,
                        page_end=chunk.page_end,
                        paragraph_start=chunk.paragraph_start,
                        paragraph_end=chunk.paragraph_end,
                        heading_path=chunk.heading_path,
                        ocr_confidence=chunk.ocr_confidence,
                    )
                )
            complete = await self.trace(
                trace_id, kb, request.query, stages, [str(item.chunk_id) for item in evidence], None
            )
            return RetrievalResult(trace_id=trace_id, trace_complete=complete, evidence=evidence)
        except ProcessingError as exc:
            await self.trace(trace_id, kb, request.query, stages, [], exc.code)
            raise UpstreamServiceError(
                "检索服务暂时不可用，请稍后再试", error_key=exc.code
            ) from None

    @staticmethod
    def event(stage: str, candidates: list[tuple[UUID, float]], start: float) -> dict[str, object]:
        return {
            "stage": stage,
            "elapsed_ms": round((time.monotonic() - start) * 1000),
            "candidates": [
                {"chunk_id": str(chunk), "rank": i + 1, "score": score}
                for i, (chunk, score) in enumerate(candidates)
            ],
        }
