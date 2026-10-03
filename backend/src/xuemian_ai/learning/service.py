import asyncio
import hashlib
import hmac
import time
from collections.abc import AsyncGenerator
from contextlib import aclosing
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import UUID, uuid4

from anyio import CancelScope
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from xuemian_ai.accounts.models import User
from xuemian_ai.core.config import Settings
from xuemian_ai.core.errors import AppError, ConflictError, NotFoundError, UpstreamServiceError
from xuemian_ai.core.responses import PageResponse, page_response
from xuemian_ai.document_processing.models import (
    AIProcessingConsent,
    DocumentChunk,
    DocumentProcessingVersion,
)
from xuemian_ai.document_processing.retrieval import RetrievalService
from xuemian_ai.document_processing.schemas import AIConsentView, EvidenceChunk, RetrievalRequest
from xuemian_ai.file_management.models import FileAsset, KnowledgeBaseFile
from xuemian_ai.knowledge_bases.models import KnowledgeBase
from xuemian_ai.learning.generation import (
    REFUSAL,
    REFUSAL_EN,
    AnswerProvider,
    InputContext,
    QwenAnswerProvider,
    prompt_manifest,
    validate_answer,
)
from xuemian_ai.learning.models import LearningConversation, LearningTurn
from xuemian_ai.learning.schemas import (
    AnswerCitation,
    AnswerRequest,
    AnswerStreamEvent,
    ConversationCreate,
    ConversationDetail,
    ConversationView,
    GeneratedAnswer,
    TurnView,
)
from xuemian_ai.profiles.models import UserProfile

LEARNING_NOTICE = (
    "使用 AI 问答时，您的问题、当前会话最近六条问题和选定资料中的检索片段会发送给千问，"
    "用于生成回答；资料检索还会发送检索问题与候选片段用于向量和重排。"
    "您也将确认既有资料解析说明：待 OCR 的 PDF 页面图片和文档文本会用于文字识别与生成向量。"
    "请确认您有权处理这些内容。系统不会自动创建笔记，也不会将本次输入保存为默认画像。"
)


class LearningService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
        user_id: UUID,
        request_id: str | None = None,
        provider: AnswerProvider | None = None,
        retrieval: RetrievalService | None = None,
    ) -> None:
        self.sessions, self.settings, self.user_id = sessions, settings, user_id
        self.provider = provider or QwenAnswerProvider(settings)
        self.request_id, self.retrieval = request_id, retrieval

    async def consent(self, version: str | None = None) -> AIConsentView:
        async with self.sessions() as session, session.begin():
            if version is not None:
                if version != self.settings.learning_consent_version:
                    raise ConflictError(
                        "AI 说明版本已变化，请重新确认", error_key="AI_CONSENT_VERSION_CHANGED"
                    )
                for terms in {version, self.settings.ai_processing_terms_version}:
                    await session.execute(
                        insert(AIProcessingConsent)
                        .values(
                            user_id=self.user_id,
                            terms_version=terms,
                            confirmed_at=datetime.now(UTC),
                        )
                        .on_conflict_do_nothing(constraint="uq_ai_processing_consent")
                    )
            confirmed = bool(
                await session.scalar(
                    select(AIProcessingConsent.id).where(
                        AIProcessingConsent.user_id == self.user_id,
                        AIProcessingConsent.terms_version == self.settings.learning_consent_version,
                    )
                )
            )
        return AIConsentView(
            confirmed=confirmed,
            terms_version=self.settings.learning_consent_version,
            notice=LEARNING_NOTICE,
        )

    async def conversation(
        self, session: AsyncSession, identifier: UUID, *, lock: bool = False
    ) -> LearningConversation:
        query = select(LearningConversation).where(
            LearningConversation.id == identifier,
            LearningConversation.user_id == self.user_id,
            LearningConversation.deleted_at.is_(None),
        )
        if lock:
            query = query.with_for_update()
        result = await session.scalar(query)
        if result is None:
            raise NotFoundError(error_key="LEARNING_CONVERSATION_NOT_FOUND")
        return result

    async def scope(
        self, session: AsyncSession, mode: str, kb: UUID | None, files: list[str]
    ) -> None:
        if mode == "general":
            return
        allowed = await session.scalar(
            select(KnowledgeBase.id).where(
                KnowledgeBase.id == kb,
                KnowledgeBase.owner_user_id == self.user_id,
                KnowledgeBase.deleted_at.is_(None),
            )
        )
        if allowed is None:
            raise NotFoundError(error_key="KNOWLEDGE_BASE_NOT_FOUND")
        if files:
            ids = (
                await session.scalars(
                    select(KnowledgeBaseFile.id)
                    .join(
                        FileAsset,
                        FileAsset.id == KnowledgeBaseFile.file_asset_id,
                    )
                    .where(
                        KnowledgeBaseFile.knowledge_base_id == kb,
                        KnowledgeBaseFile.id.in_([UUID(f) for f in files]),
                        KnowledgeBaseFile.deleted_at.is_(None),
                        FileAsset.deleted_at.is_(None),
                        FileAsset.owner_user_id == self.user_id,
                    )
                )
            ).all()
            if {str(i) for i in ids} != set(files):
                raise NotFoundError(error_key="KNOWLEDGE_FILE_NOT_FOUND")

    async def create(self, body: ConversationCreate) -> ConversationView:
        async with self.sessions() as session, session.begin():
            files = [str(f) for f in body.file_ids]
            await self.scope(session, body.mode, body.knowledge_base_id, files)
            item = LearningConversation(
                user_id=self.user_id,
                mode=body.mode,
                knowledge_base_id=body.knowledge_base_id,
                file_ids=files,
                title="新问答",
                created_by=self.user_id,
                updated_by=self.user_id,
            )
            session.add(item)
            await session.flush()
            return ConversationView.model_validate(item)

    async def list_conversations(self, page: int, page_size: int) -> PageResponse[ConversationView]:
        async with self.sessions() as session:
            filters = (
                LearningConversation.user_id == self.user_id,
                LearningConversation.deleted_at.is_(None),
            )
            total = (
                await session.scalar(
                    select(func.count()).select_from(LearningConversation).where(*filters)
                )
                or 0
            )
            rows = (
                await session.scalars(
                    select(LearningConversation)
                    .where(*filters)
                    .order_by(
                        LearningConversation.updated_at.desc(), LearningConversation.id.desc()
                    )
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
            return page_response(
                [ConversationView.model_validate(row) for row in rows],
                page=page,
                page_size=page_size,
                total=total,
            )

    async def rename(self, identifier: UUID, title: str) -> ConversationView:
        async with self.sessions() as session, session.begin():
            item = await self.conversation(session, identifier, lock=True)
            item.title, item.updated_by, item.updated_at = title, self.user_id, datetime.now(UTC)
            await session.flush()
            return ConversationView.model_validate(item)

    async def delete(self, identifier: UUID) -> None:
        async with self.sessions() as session, session.begin():
            item = await self.conversation(session, identifier, lock=True)
            item.deleted_at, item.deleted_by = datetime.now(UTC), self.user_id

    async def evidence(
        self,
        session: AsyncSession,
        item: LearningConversation,
        ids: list[UUID],
        *,
        lock: bool = False,
    ) -> dict[UUID, EvidenceChunk]:
        if item.mode == "general" or not ids:
            return {}
        retrieval = self.retrieval or RetrievalService(
            self.sessions, self.settings, self.user_id, self.request_id
        )
        try:
            query = retrieval.authorized_chunks(
                cast(UUID, item.knowledge_base_id), [UUID(f) for f in item.file_ids]
            ).where(DocumentChunk.id.in_(ids))
            if lock:
                query = query.with_for_update(
                    of=(
                        DocumentChunk,
                        DocumentProcessingVersion,
                        KnowledgeBaseFile,
                        FileAsset,
                        KnowledgeBase,
                    )
                )
            rows = (await session.execute(query)).all()
            return {
                chunk.id: EvidenceChunk(
                    chunk_id=chunk.id,
                    file_id=binding.id,
                    file_name=binding.display_name,
                    processing_version_id=chunk.processing_version_id,
                    content=chunk.content,
                    score=0,
                    source_kind=chunk.source_kind,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    paragraph_start=chunk.paragraph_start,
                    paragraph_end=chunk.paragraph_end,
                    heading_path=chunk.heading_path,
                    ocr_confidence=chunk.ocr_confidence,
                )
                for chunk, binding in rows
            }
        finally:
            if self.retrieval is None:
                await retrieval.vector_store.close()

    async def view(
        self, session: AsyncSession, item: LearningConversation, turn: LearningTurn
    ) -> TurnView:
        ids = [UUID(str(c["chunk_id"])) for c in turn.citations]
        available = await self.evidence(session, item, ids)
        return TurnView(
            id=turn.id,
            request_key=turn.request_key,
            language=cast("LiteralLanguage", turn.model_parameters.get("answer_language", "zh")),
            question=turn.question,
            status=cast(
                "LiteralStatus",
                "failed"
                if turn.status == "processing" and turn.lease_expires_at <= datetime.now(UTC)
                else turn.status,
            ),
            answer=turn.answer,
            refused=turn.refused,
            source_label="用户资料" if item.mode == "materials" else "模型通用知识",
            citations=[
                AnswerCitation(
                    number=int(c["number"]),
                    available=UUID(str(c["chunk_id"])) in available,
                    evidence=available.get(UUID(str(c["chunk_id"]))),
                )
                for c in turn.citations
            ],
            trace_id=turn.trace_id,
            trace_complete=turn.trace_complete,
            error_code="ANSWER_LEASE_EXPIRED"
            if turn.status == "processing" and turn.lease_expires_at <= datetime.now(UTC)
            else turn.error_code,
            feedback=cast("LiteralFeedback", turn.feedback),
            created_at=turn.created_at,
        )

    async def detail(self, identifier: UUID) -> ConversationDetail:
        async with self.sessions() as session:
            item = await self.conversation(session, identifier)
            turns = (
                await session.scalars(
                    select(LearningTurn)
                    .where(LearningTurn.conversation_id == identifier)
                    .order_by(LearningTurn.created_at, LearningTurn.id)
                )
            ).all()
            return ConversationDetail(
                conversation=ConversationView.model_validate(item),
                turns=[await self.view(session, item, t) for t in turns],
            )

    async def feedback(self, identifier: UUID, turn_id: UUID, feedback: str | None) -> TurnView:
        async with self.sessions() as session, session.begin():
            item = await self.conversation(session, identifier, lock=True)
            turn = await session.scalar(
                select(LearningTurn)
                .where(LearningTurn.id == turn_id, LearningTurn.conversation_id == identifier)
                .with_for_update()
            )
            if turn is None:
                raise NotFoundError(error_key="LEARNING_TURN_NOT_FOUND")
            if turn.status != "succeeded":
                raise ConflictError("只能反馈已完成的回答", error_key="ANSWER_NOT_COMPLETED")
            turn.feedback = feedback
            return await self.view(session, item, turn)

    async def prepare_answer(self, identifier: UUID, body: AnswerRequest) -> "PreparedAnswer":
        digest = hmac.new(
            self.settings.auth_fingerprint_secret.get_secret_value().encode(),
            body.question.encode(),
            hashlib.sha256,
        ).hexdigest()
        now, token = datetime.now(UTC), uuid4()
        async with self.sessions() as session, session.begin():
            item = await self.conversation(session, identifier, lock=True)
            await self.scope(session, item.mode, item.knowledge_base_id, item.file_ids)
            turns = list(
                (
                    await session.scalars(
                        select(LearningTurn)
                        .where(LearningTurn.conversation_id == identifier)
                        .order_by(LearningTurn.created_at, LearningTurn.id)
                        .with_for_update()
                    )
                ).all()
            )
            turn = next((t for t in turns if t.request_key == body.request_key), None)
            preference = await session.scalar(
                select(UserProfile.preferred_language).where(UserProfile.user_id == self.user_id)
            )
            language = body.language or (
                cast("LiteralLanguage", turn.model_parameters.get("answer_language", "zh"))
                if turn is not None
                else "en"
                if preference == "en-US"
                else "zh"
            )
            body = body.model_copy(update={"language": language})
            if turn is not None and (
                turn.question_digest != digest
                or turn.model_parameters.get("answer_language", "zh") != body.language
            ):
                raise ConflictError(
                    "同一请求标识不能用于不同问题", error_key="ANSWER_REQUEST_CONFLICT"
                )
            if turn is not None and turn.status == "succeeded":
                return PreparedAnswer(identifier, body, replay=await self.view(session, item, turn))
            for old in turns:
                if old.status == "processing":
                    if old.lease_expires_at > now:
                        raise ConflictError(
                            "此会话已有问题正在回答，请稍后再试", error_key="ANSWER_IN_PROGRESS"
                        )
                    old.status, old.error_code = "failed", "ANSWER_LEASE_EXPIRED"
            await session.flush()
            if len(turns) >= 100 and turn is None:
                raise ConflictError("此会话已达 100 轮，请新建会话", error_key="CONVERSATION_LIMIT")
            if turn is None:
                turn = LearningTurn(
                    conversation_id=identifier,
                    request_key=body.request_key,
                    question=body.question,
                    question_digest=digest,
                    attempt_count=1,
                )
                session.add(turn)
            else:
                turn.attempt_count += 1
            turn.status, turn.lease_token, turn.lease_expires_at = (
                "processing",
                token,
                now + timedelta(seconds=self.settings.learning_request_timeout_seconds + 30),
            )
            turn.error_code, turn.answer, turn.citations = None, None, []
            turn.agent_key, turn.scene_key = "content_analyzer", "learning_quick_answer"
            turn.prompt_manifest = prompt_manifest()
            turn.model_parameters = {
                "model": self.settings.learning_answer_model,
                "temperature": 0,
                "enable_thinking": False,
                "answer_language": body.language,
            }
            previous = [t.question for t in turns if t.status == "succeeded"][-6:]
            if not turns and item.title == "新问答":
                item.title = body.question[:40]
            item.updated_at = now
            await session.flush()
            turn_id = turn.id
            mode, kb, files = item.mode, item.knowledge_base_id, [UUID(f) for f in item.file_ids]
            started = await self.view(session, item, turn)
        return PreparedAnswer(identifier, body, turn_id, token, mode, kb, files, previous, started)

    async def answer(self, identifier: UUID, body: AnswerRequest) -> TurnView:
        prepared = await self.prepare_answer(identifier, body)
        async with aclosing(self.run_answer(prepared, streaming=False)) as stream:
            async for event in stream:
                if event.type == "completed" and event.turn is not None:
                    return event.turn
        raise UpstreamServiceError(error_key="ANSWER_FAILED")

    async def stream_answer(
        self, prepared: "PreparedAnswer"
    ) -> AsyncGenerator[AnswerStreamEvent, None]:
        try:
            async with aclosing(self.run_answer(prepared, streaming=True)) as stream:
                async for event in stream:
                    yield event
        except AppError as exc:
            yield AnswerStreamEvent(type="failed", error_code=exc.error_key, message=exc.message)

    async def run_answer(
        self, prepared: "PreparedAnswer", *, streaming: bool
    ) -> AsyncGenerator[AnswerStreamEvent, None]:
        if prepared.replay is not None:
            async with self.sessions() as session, session.begin():
                await self.active_user(session)
                item = await self.conversation(session, prepared.identifier, lock=True)
                await self.scope(session, item.mode, item.knowledge_base_id, item.file_ids)
                turn = await session.get(LearningTurn, prepared.replay.id, with_for_update=True)
                if turn is None or turn.status != "succeeded":
                    raise ConflictError(error_key="ANSWER_REQUEST_CONFLICT")
                replay = await self.view(session, item, turn)
            yield AnswerStreamEvent(type="started", turn=replay)
            yield AnswerStreamEvent(type="completed", turn=replay)
            return
        body = prepared.body
        turn_id, token = prepared.turn_id, prepared.token
        mode, kb, files, previous = prepared.mode, prepared.kb, prepared.files, prepared.previous
        start = time.monotonic()
        trace_id: UUID | None = None
        trace_complete = False
        evidence: list[EvidenceChunk] = []
        try:
            yield AnswerStreamEvent(type="started", turn=prepared.started)
            async with asyncio.timeout(self.settings.learning_request_timeout_seconds):
                if mode == "materials":
                    retrieval = self.retrieval or RetrievalService(
                        self.sessions, self.settings, self.user_id, self.request_id
                    )
                    query = body.question
                    if previous:
                        query = (body.question + "\n此前问题：" + "\n".join(previous[-2:]))[:2000]
                    result = await retrieval.search(
                        cast(UUID, kb), RetrievalRequest(query=query, file_ids=files, top_n=8)
                    )
                    trace_id, trace_complete, evidence = (
                        result.trace_id,
                        result.trace_complete,
                        result.evidence,
                    )
                context = InputContext(
                    mode=cast("LiteralMode", mode),
                    question=body.question,
                    answer_language=cast("LiteralLanguage", body.language),
                    previous_questions=previous,
                    evidence=evidence,
                )
                if mode == "materials" and not evidence:
                    generated = GeneratedAnswer(
                        answer=REFUSAL if body.language == "zh" else REFUSAL_EN,
                        refused=True,
                        citation_ids=[],
                    )
                elif streaming:
                    generated = None
                    async with aclosing(self.provider.stream(context)) as parts:
                        async for part in parts:
                            if isinstance(part, str):
                                async with self.sessions() as session, session.begin():
                                    await self.publication_guard(session, prepared, evidence)
                                yield AnswerStreamEvent(type="delta", delta=part)
                            else:
                                generated = validate_answer(part, context)
                    if generated is None:
                        raise UpstreamServiceError(error_key="ANSWER_OUTPUT_INCOMPLETE")
                else:
                    generated = validate_answer(await self.provider.generate(context), context)
                assert generated is not None
                async with self.sessions() as session, session.begin():
                    item, turn = await self.publication_guard(session, prepared, evidence)
                    turn.status, turn.answer, turn.refused = (
                        "succeeded",
                        generated.answer,
                        generated.refused,
                    )
                    turn.trace_id, turn.trace_complete = trace_id, trace_complete
                    turn.citations = [
                        {"number": index, "chunk_id": str(evidence[index - 1].chunk_id)}
                        for index in generated.citation_ids
                    ]
                    turn.elapsed_ms = round((time.monotonic() - start) * 1000)
                    item.updated_at = datetime.now(UTC)
                    completed = await self.view(session, item, turn)
                yield AnswerStreamEvent(type="completed", turn=completed)
        except (Exception, asyncio.CancelledError, GeneratorExit) as exc:
            code = (
                exc.error_key
                if isinstance(exc, AppError)
                else "ANSWER_CANCELLED"
                if isinstance(exc, (asyncio.CancelledError, GeneratorExit))
                else "ANSWER_TIMEOUT"
                if isinstance(exc, TimeoutError)
                else "ANSWER_FAILED"
            )
            with CancelScope(shield=True):
                async with self.sessions() as session, session.begin():
                    failed_turn = await session.get(LearningTurn, turn_id, with_for_update=True)
                    if (
                        failed_turn is not None
                        and failed_turn.lease_token == token
                        and failed_turn.status == "processing"
                    ):
                        failed_turn.status, failed_turn.error_code = "failed", code
                        failed_turn.trace_id, failed_turn.trace_complete = trace_id, trace_complete
                        failed_turn.elapsed_ms = round((time.monotonic() - start) * 1000)
            if isinstance(exc, (AppError, asyncio.CancelledError, GeneratorExit)):
                raise
            raise UpstreamServiceError("回答未完成，请重试", error_key=code) from None

    async def cancel_prepared(self, prepared: "PreparedAnswer") -> None:
        """Response lifetime cleanup also covers an iterator never entered."""
        if prepared.turn_id is None or prepared.token is None:
            return
        with CancelScope(shield=True):
            async with self.sessions() as session, session.begin():
                turn = await session.get(LearningTurn, prepared.turn_id, with_for_update=True)
                if (
                    turn is not None
                    and turn.status == "processing"
                    and turn.lease_token == prepared.token
                ):
                    turn.status, turn.error_code = "failed", "ANSWER_CANCELLED"

    async def active_user(self, session: AsyncSession) -> None:
        active = await session.scalar(
            select(User.id)
            .where(User.id == self.user_id, User.deleted_at.is_(None), User.status == "active")
            .with_for_update()
        )
        if active is None:
            raise NotFoundError(error_key="USER_NOT_FOUND")

    async def publication_guard(
        self, session: AsyncSession, prepared: "PreparedAnswer", evidence: list[EvidenceChunk]
    ) -> tuple[LearningConversation, LearningTurn]:
        identifier, turn_id, token = prepared.identifier, prepared.turn_id, prepared.token
        await self.active_user(session)
        item = await self.conversation(session, identifier, lock=True)
        turn = await session.get(LearningTurn, turn_id, with_for_update=True)
        if (
            turn is None
            or turn.lease_token != token
            or turn.status != "processing"
            or turn.lease_expires_at <= datetime.now(UTC)
        ):
            raise ConflictError("回答请求已过期，请重试", error_key="ANSWER_LEASE_EXPIRED")
        await self.scope(session, item.mode, item.knowledge_base_id, item.file_ids)
        current = await self.evidence(session, item, [e.chunk_id for e in evidence], lock=True)
        if any(
            e.chunk_id not in current
            or current[e.chunk_id].processing_version_id != e.processing_version_id
            for e in evidence
        ):
            raise ConflictError("资料已变化，请重新提问", error_key="ANSWER_SOURCE_CHANGED")
        return item, turn


LiteralLanguage = Literal["zh", "en"]
LiteralMode = Literal["materials", "general"]
LiteralStatus = Literal["processing", "succeeded", "failed"]
LiteralFeedback = Literal["helpful", "unhelpful"] | None


@dataclass
class PreparedAnswer:
    identifier: UUID
    body: AnswerRequest
    turn_id: UUID | None = None
    token: UUID | None = None
    mode: str = "general"
    kb: UUID | None = None
    files: list[UUID] = field(default_factory=list)
    previous: list[str] = field(default_factory=list)
    started: TurnView | None = None
    replay: TurnView | None = None
