"""工单事务边界；授权、正文提取和版本锁必须在同一个短事务内完成。"""

import json
from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from xuemian_ai.accounts.models import User
from xuemian_ai.ai_quality.crypto import SnapshotCipher
from xuemian_ai.ai_quality.diagnostics import offline_replay, validate_chunks
from xuemian_ai.ai_quality.models import (
    AIQualityCase,
    AIQualityCaseEvent,
    DiagnosticAccessGrant,
    DiagnosticAudit,
    DiagnosticReplay,
    DiagnosticSnapshot,
)
from xuemian_ai.ai_quality.policy import (
    TECHNICAL_CODES,
    check_version,
    effective_closed,
    transition_allowed,
    validate_text,
)
from xuemian_ai.ai_quality.schemas import (
    AccessRequest,
    AdminCaseDetail,
    AdminMessageCreate,
    AssignmentRequest,
    AuditView,
    CaseCreate,
    CaseView,
    EventView,
    GrantDecision,
    GrantRevoke,
    GrantView,
    MessageCreate,
    QualityOverview,
    ReplayRequest,
    ReplayView,
    SnapshotRequest,
    SnapshotView,
    TransitionRequest,
    UserCaseDetail,
)
from xuemian_ai.core.errors import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    TooManyRequestsError,
)
from xuemian_ai.core.responses import PageResponse, page_response
from xuemian_ai.document_processing.models import RetrievalTrace
from xuemian_ai.learning.models import LearningConversation, LearningTurn
from xuemian_ai.learning.result_sources import (
    LearningResultSource,
    TraceMetadata,
    load_learning_result,
)
from xuemian_ai.learning_assets.policy import fingerprint


class QualityService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        user: User,
        settings: Any,
        request_id: str | None = None,
    ) -> None:
        self.sessions, self.user, self.settings = sessions, user, settings
        self.request_id = request_id

    def _role(self, admin: bool) -> None:
        if self.user.role != ("admin" if admin else "user"):
            raise ForbiddenError(error_key="QUALITY_ROLE_FORBIDDEN")

    @asynccontextmanager
    async def _tx(
        self,
        action: str,
        case_id: UUID | None = None,
        fields: list[str] | None = None,
    ) -> AsyncIterator[AsyncSession]:
        try:
            async with self.sessions.begin() as session:
                yield session
                self._audit(session, action, "allowed", case_id, fields=fields)
        except AppError as exc:
            # 拒绝审计使用独立事务，不能随被拒绝的业务事务一起回滚。
            async with self.sessions.begin() as session:
                self._audit(session, action, "denied", case_id, exc.error_key, fields)
            exc.headers = {**(exc.headers or {}), "Cache-Control": "no-store"}
            raise

    def _audit(
        self,
        session: AsyncSession,
        action: str,
        outcome: str,
        case_id: UUID | None,
        reason: str | None = None,
        fields: list[str] | None = None,
    ) -> None:
        session.add(
            DiagnosticAudit(
                actor_id=self.user.id,
                case_id=case_id,
                action=action,
                outcome=outcome,
                reason_code=reason,
                fields=fields or [],
                version=None,
                request_id=self.request_id,
                occurred_at=datetime.now(UTC),
            )
        )

    async def _case(
        self, session: AsyncSession, case_id: UUID, admin: bool = False
    ) -> AIQualityCase:
        self._role(admin)
        query = select(AIQualityCase).where(AIQualityCase.id == case_id)
        if not admin:
            query = query.where(AIQualityCase.user_id == self.user.id)
        obj = await session.scalar(query.with_for_update())
        if obj is None:
            raise NotFoundError(error_key="QUALITY_CASE_UNAVAILABLE")
        return obj

    def _closed(self, obj: AIQualityCase) -> bool:
        return effective_closed(
            obj.status, obj.resolved_at, self.settings.ai_quality_confirmation_days
        )

    def _open(self, obj: AIQualityCase) -> None:
        if self._closed(obj):
            raise ConflictError(error_key="QUALITY_CASE_CLOSED")

    async def _source(self, session: AsyncSession, obj: AIQualityCase) -> LearningResultSource:
        owner = await session.scalar(
            select(User)
            .where(
                User.id == obj.user_id,
                User.role == "user",
                User.status == "active",
                User.deleted_at.is_(None),
            )
            .with_for_update(read=True)
        )
        if owner is None:
            raise ConflictError(error_key="SOURCE_UNAVAILABLE")
        # 学习正文只能经业务适配器取得；行共享锁阻止本事务内来源被删除。
        await session.scalar(
            select(LearningConversation)
            .join(LearningTurn, LearningTurn.conversation_id == LearningConversation.id)
            .where(LearningTurn.id == obj.source_id)
            .with_for_update(read=True)
        )
        source = await load_learning_result(session, obj.user_id, obj.source_id, obj.trace_id)
        if source.knowledge_base_id != obj.knowledge_base_id:
            raise ConflictError(error_key="SOURCE_UNAVAILABLE")
        await validate_chunks(
            session, obj.user_id, obj.knowledge_base_id, source.trace.final_chunk_ids
        )
        return source

    def _event(
        self,
        session: AsyncSession,
        obj: AIQualityCase,
        action: str,
        content: str | None = None,
        visibility: str = "user",
    ) -> None:
        item = AIQualityCaseEvent(
            id=uuid4(),
            case_id=obj.id,
            actor_id=self.user.id,
            action=action,
            visibility=visibility,
            version=obj.version,
        )
        if content is not None:
            validate_text(content)
            item.key_id, item.ciphertext = SnapshotCipher(self.settings).encrypt(
                f"event:{obj.id}:{item.id}", {"content": content}
            )
        session.add(item)

    def _view(self, obj: AIQualityCase) -> CaseView:
        return CaseView.model_validate(obj)

    def _grant_view(self, grant: DiagnosticAccessGrant, obj: AIQualityCase) -> GrantView:
        result = GrantView.model_validate(grant)
        if result.status in {"pending", "active"} and (
            result.expires_at <= datetime.now(UTC) or self._closed(obj)
        ):
            result.status = "expired"
        return result

    async def _grants(self, session: AsyncSession, obj: AIQualityCase) -> list[GrantView]:
        rows = await session.scalars(
            select(DiagnosticAccessGrant)
            .where(DiagnosticAccessGrant.case_id == obj.id)
            .order_by(DiagnosticAccessGrant.created_at, DiagnosticAccessGrant.id)
        )
        return [self._grant_view(row, obj) for row in rows]

    async def _grant(
        self,
        session: AsyncSession,
        obj: AIQualityCase,
        grant_id: UUID,
        version: int,
        fields: list[str] | None = None,
    ) -> DiagnosticAccessGrant:
        grant = await session.scalar(
            select(DiagnosticAccessGrant)
            .where(
                DiagnosticAccessGrant.id == grant_id,
                DiagnosticAccessGrant.case_id == obj.id,
            )
            .with_for_update()
        )
        if grant is None:
            raise NotFoundError(error_key="QUALITY_GRANT_UNAVAILABLE")
        check_version(grant.version, version)
        if fields is not None:
            if (
                self._closed(obj)
                or obj.access_expires_at <= datetime.now(UTC)
                or (grant.status != "active" or grant.expires_at <= datetime.now(UTC))
            ):
                raise ForbiddenError(error_key="QUALITY_GRANT_INACTIVE")
            if not set(fields).issubset(grant.fields):
                raise ForbiddenError(error_key="QUALITY_GRANT_SCOPE_FORBIDDEN")
        return grant

    async def _statement(self, obj: AIQualityCase) -> dict[str, Any]:
        if obj.statement_key_id is None or obj.statement_ciphertext is None:
            return {}
        return SnapshotCipher(self.settings).decrypt(
            f"statement:{obj.id}", obj.statement_key_id, obj.statement_ciphertext
        )

    async def _events(
        self, session: AsyncSession, obj: AIQualityCase, admin: bool
    ) -> list[EventView]:
        query = select(AIQualityCaseEvent).where(AIQualityCaseEvent.case_id == obj.id)
        if not admin:
            query = query.where(AIQualityCaseEvent.visibility == "user")
        rows = await session.scalars(
            query.order_by(AIQualityCaseEvent.created_at, AIQualityCaseEvent.id)
        )
        result = []
        # 管理员初始详情不含用户补充正文；只有有效基础授权允许解密。
        body_allowed = not admin or any(
            grant.status == "active" and "query" in grant.fields
            for grant in await self._grants(session, obj)
        )
        for row in rows:
            content = None
            if row.key_id and row.ciphertext and body_allowed:
                content = SnapshotCipher(self.settings).decrypt(
                    f"event:{obj.id}:{row.id}", row.key_id, row.ciphertext
                )["content"]
            result.append(
                EventView(
                    id=row.id,
                    action=row.action,
                    visibility=cast(Any, row.visibility),
                    actor_id=row.actor_id,
                    version=row.version,
                    content=content,
                    created_at=row.created_at,
                )
            )
        return result

    async def create(self, body: CaseCreate) -> UserCaseDetail:
        async with self._tx("case_create") as session:
            self._role(False)
            validate_text(body.description)
            if body.expected_result:
                validate_text(body.expected_result)
            # 同一用户的创建操作串行化，覆盖双击和不同 request_key 的同源并发。
            await session.scalar(select(User).where(User.id == self.user.id).with_for_update())
            fp = fingerprint(body.model_dump(mode="json", exclude={"request_key"}))
            existing = await session.scalar(
                select(AIQualityCase).where(
                    AIQualityCase.user_id == self.user.id,
                    AIQualityCase.request_key == body.request_key,
                )
            )
            if existing:
                if existing.input_digest != fp:
                    raise ConflictError(error_key="QUALITY_REQUEST_KEY_CONFLICT")
                return await self._user_detail(session, existing)
            source = await load_learning_result(
                session, self.user.id, body.source_id, body.trace_id
            )
            active = await session.scalar(
                select(AIQualityCase)
                .where(
                    AIQualityCase.user_id == self.user.id,
                    AIQualityCase.source_id == body.source_id,
                    AIQualityCase.trace_id == body.trace_id,
                    AIQualityCase.status != "closed",
                )
                .with_for_update()
            )
            if active:
                return await self._user_detail(session, active)
            count = await session.scalar(
                select(func.count())
                .select_from(AIQualityCase)
                .where(
                    AIQualityCase.user_id == self.user.id,
                    AIQualityCase.created_at >= datetime.now(UTC) - timedelta(hours=1),
                )
            )
            if (count or 0) >= 20:
                raise TooManyRequestsError(retry_after=3600, error_key="QUALITY_RATE_LIMITED")
            now, identity = datetime.now(UTC), uuid4()
            cipher = SnapshotCipher(self.settings)
            key_id, ciphertext = cipher.encrypt(
                f"statement:{identity}",
                {
                    "description": body.description,
                    "expected_result": body.expected_result,
                },
            )
            obj = AIQualityCase(
                id=identity,
                user_id=self.user.id,
                source_type=body.source_type,
                source_id=body.source_id,
                trace_id=body.trace_id,
                knowledge_base_id=source.knowledge_base_id,
                case_number="AQ-" + identity.hex.upper(),
                category=body.category,
                status="submitted",
                version=1,
                request_key=body.request_key,
                input_digest=fp,
                strategy_version=source.trace.strategy_version,
                trace_metadata=source.trace.model_dump(mode="json"),
                statement_key_id=key_id,
                statement_ciphertext=ciphertext,
                access_expires_at=now + timedelta(days=30),
            )
            session.add(obj)
            await session.flush()
            await self._source(session, obj)
            grant = DiagnosticAccessGrant(
                id=uuid4(),
                case_id=obj.id,
                fields=["query", "final_output", "final_citations"],
                chunk_ids=[],
                reason="排查本次资料问答质量，仅限管理员，最长30天或工单关闭前",
                status="active",
                version=1,
                expires_at=obj.access_expires_at,
                confirmed_at=now,
            )
            session.add(grant)
            key_id, ciphertext = cipher.encrypt(
                f"grant:{obj.id}:{grant.id}",
                {
                    "query": source.query,
                    "final_output": source.final_output,
                    "final_citations": source.final_citations,
                },
            )
            session.add(DiagnosticSnapshot(grant_id=grant.id, key_id=key_id, ciphertext=ciphertext))
            trace = await session.scalar(
                select(RetrievalTrace).where(RetrievalTrace.id == obj.trace_id).with_for_update()
            )
            if trace:
                trace.retained_by_case = True
                trace.expires_at = trace.occurred_at + timedelta(days=180)
            self._event(session, obj, "case_created")
            await session.flush()
            return await self._user_detail(session, obj)

    async def _user_detail(self, session: AsyncSession, obj: AIQualityCase) -> UserCaseDetail:
        statement = await self._statement(obj)
        return UserCaseDetail(
            **self._view(obj).model_dump(),
            description=statement.get("description"),
            expected_result=statement.get("expected_result"),
            events=await self._events(session, obj, False),
            grants=await self._grants(session, obj),
        )

    async def user_detail(self, case_id: UUID) -> UserCaseDetail:
        async with self._tx("case_user_detail", case_id) as session:
            return await self._user_detail(session, await self._case(session, case_id))

    async def list_cases(
        self,
        admin: bool,
        page: int,
        page_size: int,
        status: str | None = None,
        category: str | None = None,
        source_type: str | None = None,
        strategy_version: str | None = None,
        assignee_id: UUID | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        sort: str = "oldest",
    ) -> PageResponse[CaseView]:
        async with self._tx("case_queue" if admin else "case_user_list") as session:
            self._role(admin)
            query = select(AIQualityCase)
            if not admin:
                query = query.where(AIQualityCase.user_id == self.user.id)
            for field, value in [
                ("status", status),
                ("category", category),
                ("source_type", source_type),
                ("strategy_version", strategy_version),
                ("assignee_id", assignee_id),
            ]:
                if value is not None:
                    query = query.where(getattr(AIQualityCase, field) == value)
            if created_after:
                query = query.where(AIQualityCase.created_at >= created_after)
            if created_before:
                query = query.where(AIQualityCase.created_at <= created_before)
            total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
            order = (
                AIQualityCase.updated_at.desc()
                if sort == "updated"
                else (
                    AIQualityCase.created_at.desc()
                    if sort == "newest"
                    else AIQualityCase.created_at
                )
            )
            rows = await session.scalars(
                query.order_by(order, AIQualityCase.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            return page_response(
                [self._view(row) for row in rows], page=page, page_size=page_size, total=total
            )

    async def user_message(self, case_id: UUID, body: MessageCreate) -> UserCaseDetail:
        async with self._tx("case_user_message", case_id) as session:
            obj = await self._case(session, case_id)
            check_version(obj.version, body.expected_version)
            self._open(obj)
            if obj.status == "resolved":
                raise ConflictError(error_key="QUALITY_STATE_CONFLICT")
            obj.version += 1
            if obj.status == "waiting_user":
                obj.status = "triaging"
            self._event(session, obj, "user_message", body.content)
            await session.flush()
            return await self._user_detail(session, obj)

    async def user_close(
        self, case_id: UUID, version: int, withdraw: bool = False
    ) -> UserCaseDetail:
        async with self._tx("case_withdraw" if withdraw else "case_user_close", case_id) as session:
            obj = await self._case(session, case_id)
            check_version(obj.version, version)
            if withdraw and (obj.status != "submitted" or obj.assignee_id is not None):
                raise ConflictError(error_key="QUALITY_STATE_CONFLICT")
            if obj.status == "closed":
                return await self._user_detail(session, obj)
            obj.status, obj.closed_at, obj.version = "closed", datetime.now(UTC), obj.version + 1
            await self._close_grants(session, obj)
            self._event(session, obj, "case_withdrawn" if withdraw else "case_closed")
            await session.flush()
            return await self._user_detail(session, obj)

    async def _close_grants(self, session: AsyncSession, obj: AIQualityCase) -> None:
        for grant in await session.scalars(
            select(DiagnosticAccessGrant)
            .where(
                DiagnosticAccessGrant.case_id == obj.id,
                DiagnosticAccessGrant.status.in_(("pending", "active")),
            )
            .with_for_update()
        ):
            grant.status, grant.revoked_at, grant.version = (
                "revoked",
                datetime.now(UTC),
                grant.version + 1,
            )
        trace = await session.scalar(
            select(RetrievalTrace).where(RetrievalTrace.id == obj.trace_id).with_for_update()
        )
        if trace and obj.closed_at:
            trace.expires_at = min(
                trace.occurred_at + timedelta(days=180), obj.closed_at + timedelta(days=90)
            )

    async def grant_decision(
        self, case_id: UUID, grant_id: UUID, body: GrantDecision
    ) -> UserCaseDetail:
        async with self._tx("grant_decision", case_id) as session:
            obj = await self._case(session, case_id)
            self._open(obj)
            check_version(obj.version, body.expected_version)
            grant = await self._grant(session, obj, grant_id, body.expected_grant_version)
            if grant.status != "pending" or grant.expires_at <= datetime.now(UTC):
                raise ConflictError(error_key="QUALITY_GRANT_INACTIVE")
            if body.approved:
                source = await self._source(session, obj)
                chunks = await validate_chunks(
                    session,
                    obj.user_id,
                    source.knowledge_base_id,
                    [UUID(i) for i in grant.chunk_ids],
                )
                cipher = SnapshotCipher(self.settings)
                key_id, ciphertext = cipher.encrypt(
                    f"grant:{obj.id}:{grant.id}",
                    {
                        "candidate_excerpts": {
                            str(key): value.content for key, value in chunks.items()
                        }
                    },
                )
                session.add(
                    DiagnosticSnapshot(grant_id=grant.id, key_id=key_id, ciphertext=ciphertext)
                )
                grant.status, grant.confirmed_at = "active", datetime.now(UTC)
            else:
                grant.status = "rejected"
            grant.version += 1
            obj.version += 1
            if obj.status == "waiting_user":
                obj.status = "triaging"
            self._event(session, obj, "grant_approved" if body.approved else "grant_rejected")
            await session.flush()
            return await self._user_detail(session, obj)

    async def grant_revoke(
        self, case_id: UUID, grant_id: UUID, body: GrantRevoke
    ) -> UserCaseDetail:
        async with self._tx("grant_revoke", case_id) as session:
            obj = await self._case(session, case_id)
            check_version(obj.version, body.expected_version)
            grant = await self._grant(session, obj, grant_id, body.expected_grant_version)
            if grant.status not in {"pending", "active"}:
                raise ConflictError(error_key="QUALITY_GRANT_INACTIVE")
            grant.status, grant.revoked_at = "revoked", datetime.now(UTC)
            grant.version += 1
            obj.version += 1
            self._event(session, obj, "grant_revoked")
            await session.flush()
            return await self._user_detail(session, obj)

    async def admin_detail(self, case_id: UUID) -> AdminCaseDetail:
        async with self._tx("case_admin_detail", case_id) as session:
            return await self._admin_detail(session, await self._case(session, case_id, True))

    async def _admin_detail(self, session: AsyncSession, obj: AIQualityCase) -> AdminCaseDetail:
        trace, source_error = None, None
        try:
            source = await self._source(session, obj)
            trace = source.trace
        except AppError as exc:
            source_error = exc.error_key or "SOURCE_UNAVAILABLE"
        replays = await session.scalars(
            select(DiagnosticReplay)
            .where(DiagnosticReplay.case_id == obj.id)
            .order_by(DiagnosticReplay.created_at)
        )
        audits = await session.scalars(
            select(DiagnosticAudit)
            .where(DiagnosticAudit.case_id == obj.id)
            .order_by(DiagnosticAudit.occurred_at)
        )
        return AdminCaseDetail(
            **self._view(obj).model_dump(),
            trace=trace,
            source_error=source_error,
            events=await self._events(session, obj, True),
            grants=await self._grants(session, obj),
            replays=[
                ReplayView.model_validate(
                    {**row.result, "id": row.id, "created_at": row.created_at}
                )
                for row in replays
            ],
            audits=[AuditView.model_validate(row) for row in audits],
        )

    async def assign(self, case_id: UUID, body: AssignmentRequest) -> AdminCaseDetail:
        async with self._tx("case_assign", case_id) as session:
            obj = await self._case(session, case_id, True)
            self._open(obj)
            check_version(obj.version, body.expected_version)
            assignee = body.assignee_id or self.user.id
            valid = await session.scalar(
                select(User.id).where(
                    User.id == assignee,
                    User.role == "admin",
                    User.status == "active",
                    User.deleted_at.is_(None),
                )
            )
            if valid is None:
                raise NotFoundError(error_key="QUALITY_ASSIGNEE_UNAVAILABLE")
            if obj.status == "resolved":
                raise ConflictError(error_key="QUALITY_STATE_CONFLICT")
            obj.assignee_id, obj.version = assignee, obj.version + 1
            if obj.status == "submitted":
                obj.status = "triaging"
            obj.first_response_at = obj.first_response_at or datetime.now(UTC)
            self._event(session, obj, "case_assigned")
            await session.flush()
            return await self._admin_detail(session, obj)

    async def access_request(self, case_id: UUID, body: AccessRequest) -> AdminCaseDetail:
        async with self._tx("grant_request", case_id) as session:
            obj = await self._case(session, case_id, True)
            self._open(obj)
            check_version(obj.version, body.expected_version)
            if obj.status not in {"triaging", "investigating", "waiting_user"}:
                raise ConflictError(error_key="QUALITY_STATE_CONFLICT")
            validate_text(body.reason)
            source = await self._source(session, obj)
            candidates = {
                item.chunk_id for stage in source.trace.stages for item in stage.candidates
            }
            if not set(body.chunk_ids).issubset(candidates):
                raise ForbiddenError(error_key="QUALITY_GRANT_SCOPE_FORBIDDEN")
            await validate_chunks(session, obj.user_id, obj.knowledge_base_id, body.chunk_ids)
            expiry = min(
                datetime.now(UTC) + timedelta(days=body.duration_days), obj.access_expires_at
            )
            if expiry <= datetime.now(UTC):
                raise ForbiddenError(error_key="QUALITY_GRANT_INACTIVE")
            session.add(
                DiagnosticAccessGrant(
                    case_id=obj.id,
                    requester_id=self.user.id,
                    fields=["candidate_excerpts"],
                    chunk_ids=[str(i) for i in body.chunk_ids],
                    reason=body.reason,
                    status="pending",
                    version=1,
                    expires_at=expiry,
                )
            )
            obj.status, obj.version = "waiting_user", obj.version + 1
            self._event(session, obj, "grant_requested", body.reason)
            await session.flush()
            return await self._admin_detail(session, obj)

    async def snapshot(self, case_id: UUID, request: SnapshotRequest) -> SnapshotView:
        async with self._tx("snapshot_read", case_id, cast(list[str], request.fields)) as session:
            obj = await self._case(session, case_id, True)
            grant = await self._grant(
                session,
                obj,
                request.grant_id,
                request.expected_grant_version,
                cast(list[str], request.fields),
            )
            source = await self._source(session, obj)
            if "candidate_excerpts" in request.fields:
                await validate_chunks(
                    session,
                    obj.user_id,
                    source.knowledge_base_id,
                    [UUID(i) for i in grant.chunk_ids],
                )
            stored = await session.scalar(
                select(DiagnosticSnapshot).where(DiagnosticSnapshot.grant_id == grant.id)
            )
            if stored is None:
                raise NotFoundError(error_key="QUALITY_SNAPSHOT_UNAVAILABLE")
            # 不返回原始加密对象的其它字段；scope 和 grant 行锁共同防跨工单/撤销竞态。
            values = SnapshotCipher(self.settings).decrypt(
                f"grant:{obj.id}:{grant.id}", stored.key_id, stored.ciphertext
            )
            statement = await self._statement(obj) if "query" in grant.fields else {}
            return SnapshotView(
                case_id=obj.id,
                grant_id=grant.id,
                grant_version=grant.version,
                expires_at=grant.expires_at,
                values={field: values[field] for field in dict.fromkeys(request.fields)},
                description=statement.get("description"),
                expected_result=statement.get("expected_result"),
            )

    async def admin_message(self, case_id: UUID, body: AdminMessageCreate) -> AdminCaseDetail:
        async with self._tx(
            "message_public" if body.visibility == "user" else "message_internal", case_id
        ) as session:
            obj = await self._case(session, case_id, True)
            check_version(obj.version, body.expected_version)
            self._open(obj)
            if body.visibility == "admin":
                source = await self._source(session, obj)
                if any(
                    text and len(text) >= 16 and text in body.content
                    for text in [source.query, source.final_output]
                ):
                    raise ConflictError(error_key="QUALITY_BODY_COPY_FORBIDDEN")
            obj.version += 1
            obj.first_response_at = obj.first_response_at or datetime.now(UTC)
            self._event(
                session,
                obj,
                "admin_reply" if body.visibility == "user" else "internal_note",
                body.content,
                body.visibility,
            )
            await session.flush()
            return await self._admin_detail(session, obj)

    async def transition(self, case_id: UUID, body: TransitionRequest) -> AdminCaseDetail:
        async with self._tx("case_transition", case_id) as session:
            obj = await self._case(session, case_id, True)
            check_version(obj.version, body.expected_version)
            transition_allowed(obj.status, body.status)
            if body.status == "resolved":
                validate_text(cast(str, body.resolution_summary))
                if body.resolution_code in TECHNICAL_CODES:
                    evidence = False
                    if body.replay_id:
                        replay = await session.scalar(
                            select(DiagnosticReplay).where(
                                DiagnosticReplay.id == body.replay_id,
                                DiagnosticReplay.case_id == obj.id,
                                DiagnosticReplay.status == "succeeded",
                            )
                        )
                        if replay:
                            trace = TraceMetadata.model_validate(obj.trace_metadata)
                            full = offline_replay(trace, "full", [])
                            evidence = replay.result["final_chunk_ids"] != full["final_chunk_ids"]
                    if not evidence and body.deterministic_error_code:
                        try:
                            await self._source(session, obj)
                        except AppError as exc:
                            evidence = exc.error_key == body.deterministic_error_code
                    if not evidence:
                        raise ConflictError(error_key="QUALITY_ATTRIBUTION_UNVERIFIED")
                obj.resolution_code, obj.resolution_summary = (
                    body.resolution_code,
                    body.resolution_summary,
                )
                obj.resolved_at = datetime.now(UTC)
            obj.status, obj.version = body.status, obj.version + 1
            if body.status == "closed":
                obj.closed_at = datetime.now(UTC)
                await self._close_grants(session, obj)
            self._event(
                session,
                obj,
                "case_" + body.status,
                body.resolution_summary if body.status == "resolved" else None,
            )
            await session.flush()
            return await self._admin_detail(session, obj)

    async def replay(self, case_id: UUID, body: ReplayRequest) -> AdminCaseDetail:
        async with self._tx("replay_create", case_id) as session:
            obj = await self._case(session, case_id, True)
            check_version(obj.version, body.expected_version)
            self._open(obj)
            if obj.status not in {"triaging", "waiting_user", "investigating"}:
                raise ConflictError(error_key="QUALITY_STATE_CONFLICT")
            grant = await self._grant(
                session, obj, body.grant_id, body.expected_grant_version, ["query"]
            )
            source = await self._source(session, obj)
            candidates = list(
                {c.chunk_id for stage in source.trace.stages for c in stage.candidates}
            )
            await validate_chunks(session, obj.user_id, obj.knowledge_base_id, candidates)
            if body.target_chunk_ids and not set(body.target_chunk_ids).issubset(set(candidates)):
                raise ForbiddenError(error_key="QUALITY_GRANT_SCOPE_FORBIDDEN")
            result = json.loads(
                json.dumps(
                    offline_replay(source.trace, body.mode, body.target_chunk_ids), default=str
                )
            )
            result["status"] = "succeeded"
            session.add(
                DiagnosticReplay(
                    case_id=obj.id,
                    grant_id=grant.id,
                    grant_version=grant.version,
                    actor_id=self.user.id,
                    mode=body.mode,
                    status="succeeded",
                    result=result,
                    error_key=None,
                )
            )
            obj.status, obj.version = "investigating", obj.version + 1
            self._event(session, obj, "replay_completed")
            await session.flush()
            return await self._admin_detail(session, obj)

    async def overview(self) -> QualityOverview:
        async with self._tx("quality_overview") as session:
            self._role(True)
            rows = list(await session.scalars(select(AIQualityCase)))

            def quantiles(values: list[float]) -> dict[str, float | None]:
                values.sort()
                return {
                    key: values[min(int((len(values) - 1) * q), len(values) - 1)]
                    if values
                    else None
                    for key, q in [("p50", 0.5), ("p95", 0.95)]
                }

            first = [
                (row.first_response_at - row.created_at).total_seconds()
                for row in rows
                if row.first_response_at
            ]
            resolved = [
                (row.resolved_at - row.created_at).total_seconds()
                for row in rows
                if row.resolved_at
            ]
            backlog = [
                (datetime.now(UTC) - row.created_at).total_seconds()
                for row in rows
                if row.status not in {"resolved", "closed"}
            ]
            errors = await session.scalars(
                select(DiagnosticAudit.reason_code).where(DiagnosticAudit.outcome == "denied")
            )
            return QualityOverview(
                counts_by_status=dict(Counter(row.status for row in rows)),
                counts_by_category=dict(Counter(row.category for row in rows)),
                counts_by_source=dict(Counter(row.source_type for row in rows)),
                counts_by_strategy=dict(Counter(row.strategy_version for row in rows)),
                daily_counts=dict(Counter(row.created_at.date().isoformat() for row in rows)),
                first_response_seconds=quantiles(first),
                resolution_seconds=quantiles(resolved),
                backlog_seconds=quantiles(backlog),
                error_counts=dict(Counter(item for item in errors if item)),
            )
