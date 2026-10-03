"""只有显式隔离 PostgreSQL 开关允许这些合成用户/资料测试运行。"""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import delete, select, text
from test_practice_domain_integration import material_fixture

from xuemian_ai.accounts.models import User
from xuemian_ai.ai_quality.diagnostics import STRATEGY_VERSION
from xuemian_ai.ai_quality.maintenance import maintain_quality
from xuemian_ai.ai_quality.models import (
    AIQualityCase,
    DiagnosticAccessGrant,
    DiagnosticAudit,
    DiagnosticSnapshot,
)
from xuemian_ai.ai_quality.schemas import (
    AccessRequest,
    AdminMessageCreate,
    AssignmentRequest,
    CaseCreate,
    GrantDecision,
    GrantRevoke,
    MessageCreate,
    ReplayRequest,
    SnapshotRequest,
    TransitionRequest,
)
from xuemian_ai.ai_quality.service import QualityService
from xuemian_ai.api.ai_quality import router
from xuemian_ai.auth.dependencies import current_user_model
from xuemian_ai.core.config import get_settings
from xuemian_ai.core.errors import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    TooManyRequestsError,
)
from xuemian_ai.core.problem_details import register_problem_handlers
from xuemian_ai.document_processing.models import DocumentProcessingVersion, RetrievalTrace
from xuemian_ai.file_management.models import KnowledgeBaseFile
from xuemian_ai.infrastructure.database import create_database_engine, create_session_factory
from xuemian_ai.learning.models import LearningConversation, LearningTurn
from xuemian_ai.practice.service import PracticeService

pytestmark = pytest.mark.skipif(
    not os.getenv("AI_QUALITY_INTEGRATION_DB"), reason="explicit isolated database required"
)


@pytest_asyncio.fixture
async def quality():
    settings = get_settings()
    assert settings.environment == "test"
    engine = create_database_engine(settings.database_url.get_secret_value())
    sessions = create_session_factory(engine)
    async with engine.connect() as connection:
        assert (
            await connection.scalar(text("SELECT current_database()"))
            == os.environ["AI_QUALITY_INTEGRATION_DB"]
        )
    async with sessions.begin() as session:
        users = [
            User(
                username="quality" + uuid4().hex[:16],
                nickname="Synthetic",
                password_hash="not-login",
                role=role,
                status="active",
            )
            for role in ["user", "user", "admin"]
        ]
        session.add_all(users)
        await session.flush()
    owner, other, admin = users
    practice = PracticeService(sessions, owner.id, settings)
    material_set, revision, file_id, version_id = await material_fixture(practice)
    chunk_id = UUID(revision.questions[0]["source_refs"][0]["chunk_id"])
    now, trace_id, conversation_id, turn_id = datetime.now(UTC), uuid4(), uuid4(), uuid4()
    async with sessions.begin() as session:
        conversation = LearningConversation(
            id=conversation_id,
            user_id=owner.id,
            mode="materials",
            knowledge_base_id=material_set.config.knowledge_base_id,
            file_ids=[str(file_id)],
        )
        trace = RetrievalTrace(
            id=trace_id,
            user_id=owner.id,
            knowledge_base_id=material_set.config.knowledge_base_id,
            query_digest="synthetic",
            query_length=20,
            strategy_version=STRATEGY_VERSION,
            stages=[
                {"stage": "query_embedding", "elapsed_ms": 1},
                *[
                    {
                        "stage": stage,
                        "elapsed_ms": 2,
                        "candidates": [{"chunk_id": str(chunk_id), "rank": 1, "score": 0.9}],
                    }
                    for stage in ["keyword", "vector", "fusion", "rerank"]
                ],
                {"stage": "evidence_gate", "elapsed_ms": 1, "count": 1},
            ],
            final_chunk_ids=[str(chunk_id)],
            occurred_at=now,
            expires_at=now + timedelta(days=30),
            error_code=None,
        )
        session.add_all([conversation, trace])
        await session.flush()
        turn = LearningTurn(
            id=turn_id,
            conversation_id=conversation_id,
            request_key=uuid4(),
            question="Synthetic CedarQueue commit question",
            question_digest="synthetic",
            status="succeeded",
            lease_token=uuid4(),
            lease_expires_at=now,
            answer="Synthetic CedarQueue pending records can be cancelled",
            citations=[{"chunk_id": str(chunk_id)}],
            trace_id=trace_id,
            trace_complete=True,
            agent_key="content_analyzer",
            scene_key="learning_quick_answer",
            prompt_manifest={},
            model_parameters={},
        )
        session.add(turn)
    request = CaseCreate(
        source_id=turn_id,
        trace_id=trace_id,
        request_key=uuid4(),
        category="wrong_answer",
        description="合成反馈陈述",
        expected_result="合成期望",
        basic_access_confirmed=True,
    )
    data = SimpleNamespace(
        sessions=sessions,
        settings=settings,
        owner=owner,
        other=other,
        admin=admin,
        user=QualityService(sessions, owner, settings),
        operator=QualityService(sessions, admin, settings),
        outsider=QualityService(sessions, other, settings),
        request=request,
        file_id=file_id,
        version_id=version_id,
        chunk_id=chunk_id,
        turn_id=turn_id,
        conversation_id=conversation_id,
        trace_id=trace_id,
    )
    try:
        yield data
    finally:
        async with sessions.begin() as session:
            await session.execute(delete(User).where(User.id.in_([user.id for user in users])))
        await engine.dispose()


def snapshot_request(grant, fields=None):
    return SnapshotRequest(
        grant_id=grant.id,
        expected_grant_version=grant.version,
        fields=fields or ["query", "final_output"],
    )


async def test_real_create_idempotency_source_ownership_encryption_and_field_scope(quality):
    q = quality
    first, repeated = await asyncio.gather(q.user.create(q.request), q.user.create(q.request))
    assert first.id == repeated.id
    assert (
        await q.user.create(q.request.model_copy(update={"request_key": uuid4()}))
    ).id == first.id
    with pytest.raises(ConflictError):
        await q.user.create(q.request.model_copy(update={"description": "different"}))
    with pytest.raises(NotFoundError):
        await q.outsider.create(q.request.model_copy(update={"request_key": uuid4()}))
    with pytest.raises(NotFoundError):
        await q.outsider.user_detail(first.id)
    with pytest.raises(ForbiddenError):
        await q.operator.user_detail(first.id)
    grant = first.grants[0]
    permitted = await q.operator.snapshot(first.id, snapshot_request(grant, ["query"]))
    assert permitted.values == {"query": "Synthetic CedarQueue commit question"}
    assert "final_output" not in permitted.values
    with pytest.raises(ForbiddenError):
        await q.operator.snapshot(first.id, snapshot_request(grant, ["candidate_excerpts"]))
    async with q.sessions() as session:
        snapshot = await session.scalar(
            select(DiagnosticSnapshot).where(DiagnosticSnapshot.grant_id == grant.id)
        )
        case = await session.get(AIQualityCase, first.id)
        assert "Synthetic" not in snapshot.ciphertext and "合成" not in case.statement_ciphertext
        audits = list(
            await session.scalars(
                select(DiagnosticAudit).where(DiagnosticAudit.case_id == first.id)
            )
        )
        assert any(a.action == "snapshot_read" and a.outcome == "denied" for a in audits)
        assert all(a.reason_code is None or "CedarQueue" not in a.reason_code for a in audits)
    admin = await q.operator.admin_detail(first.id)
    assert "Synthetic CedarQueue" not in admin.model_dump_json()
    assert "合成反馈陈述" not in admin.model_dump_json()


async def test_extra_grant_decision_candidate_scope_revoke_and_internal_visibility(quality):
    q = quality
    created = await q.user.create(q.request)
    assigned = await q.operator.assign(
        created.id, AssignmentRequest(expected_version=created.version)
    )
    with pytest.raises(ConflictError):
        await q.user.user_close(created.id, assigned.version, True)
    waiting = await q.operator.access_request(
        created.id,
        AccessRequest(
            expected_version=assigned.version, reason="核对候选的资料依据", chunk_ids=[q.chunk_id]
        ),
    )
    pending = next(g for g in waiting.grants if "candidate_excerpts" in g.fields)
    with pytest.raises(ForbiddenError):
        await q.operator.snapshot(created.id, snapshot_request(pending, ["candidate_excerpts"]))
    approved = await q.user.grant_decision(
        created.id,
        pending.id,
        GrantDecision(
            expected_version=waiting.version, expected_grant_version=pending.version, approved=True
        ),
    )
    granted = next(g for g in approved.grants if g.id == pending.id)
    read = await q.operator.snapshot(created.id, snapshot_request(granted, ["candidate_excerpts"]))
    assert str(q.chunk_id) in read.values["candidate_excerpts"]
    noted = await q.operator.admin_message(
        created.id,
        AdminMessageCreate(
            expected_version=approved.version, visibility="admin", content="仅管理员可见的合成备注"
        ),
    )
    owner_view = await q.user.user_detail(created.id)
    assert "仅管理员可见" not in owner_view.model_dump_json()
    assert "仅管理员可见" in noted.model_dump_json()
    with pytest.raises(ConflictError):
        await q.operator.admin_message(
            created.id,
            AdminMessageCreate(
                expected_version=noted.version,
                visibility="admin",
                content="Synthetic CedarQueue pending records can be cancelled",
            ),
        )
    revoked = await q.user.grant_revoke(
        created.id,
        granted.id,
        GrantRevoke(expected_version=owner_view.version, expected_grant_version=granted.version),
    )
    newer = next(g for g in revoked.grants if g.id == granted.id)
    with pytest.raises(ForbiddenError):
        await q.operator.snapshot(created.id, snapshot_request(newer, ["candidate_excerpts"]))


@pytest.mark.parametrize(
    "change", ["source_deleted", "owner_deleted", "owner_disabled", "version_retired", "file_moved"]
)
async def test_invalid_source_denies_all_admin_body_channels(quality, change):
    q = quality
    created = await q.user.create(q.request)
    supplemented = await q.user.user_message(
        created.id,
        MessageCreate(expected_version=created.version, content="合成补充正文，应在来源失效时隐藏"),
    )
    assert any(e.content for e in (await q.operator.admin_detail(created.id)).events)
    async with q.sessions.begin() as session:
        if change == "source_deleted":
            obj = await session.get(LearningConversation, q.conversation_id)
            obj.deleted_at = datetime.now(UTC)
        elif change in {"owner_deleted", "owner_disabled"}:
            obj = await session.get(User, q.owner.id)
            if change == "owner_deleted":
                obj.deleted_at = datetime.now(UTC)
            else:
                obj.status = "disabled"
        elif change == "version_retired":
            obj = await session.get(DocumentProcessingVersion, q.version_id)
            obj.status = "retired"
        else:
            obj = await session.get(KnowledgeBaseFile, q.file_id)
            obj.deleted_at = datetime.now(UTC)
    unavailable = await q.operator.admin_detail(created.id)
    assert unavailable.source_error
    assert all(e.content is None for e in unavailable.events)
    assert "合成补充正文" not in unavailable.model_dump_json()
    with pytest.raises(AppError):
        await q.operator.snapshot(created.id, snapshot_request(supplemented.grants[0]))


async def test_offline_modes_preserve_live_turn_and_require_current_grant(quality):
    q = quality
    created = await q.user.create(q.request)
    detail = await q.operator.assign(
        created.id, AssignmentRequest(expected_version=created.version)
    )
    grant = created.grants[0]
    for mode in ["fts_only", "vector_only", "hybrid_only", "without_rerank", "full"]:
        detail = await q.operator.replay(
            created.id,
            ReplayRequest(
                expected_version=detail.version,
                grant_id=grant.id,
                expected_grant_version=grant.version,
                mode=mode,
                target_chunk_ids=[q.chunk_id],
            ),
        )
        replay = detail.replays[-1]
        assert replay.metrics["recall"] == 1.0
        assert replay.independent_latency_ms is None and not replay.causal_claim
    with pytest.raises(ConflictError):
        await q.operator.transition(
            created.id,
            TransitionRequest(
                expected_version=detail.version,
                status="resolved",
                resolution_code="rerank",
                resolution_summary="没有可证实的排名差异",
                replay_id=detail.replays[-1].id,
            ),
        )
    resolved = await q.operator.transition(
        created.id,
        TransitionRequest(
            expected_version=detail.version,
            status="resolved",
            resolution_code="not_reproduced",
            resolution_summary="合成离线对照未复现差异",
        ),
    )
    assert resolved.status == "resolved"
    closed = await q.user.user_close(created.id, resolved.version)
    assert closed.status == "closed"
    with pytest.raises(AppError):
        await q.operator.snapshot(created.id, snapshot_request(closed.grants[0]))
    async with q.sessions() as session:
        turn = await session.get(LearningTurn, q.turn_id)
        assert turn.answer == "Synthetic CedarQueue pending records can be cancelled"


async def test_http_role_matrix_no_store_and_metadata_only_queue(quality):
    q = quality
    app = FastAPI()
    app.state.infrastructure = SimpleNamespace(sessions=q.sessions)
    app.include_router(router, prefix="/api/v1")
    register_problem_handlers(app)
    app.dependency_overrides[get_settings] = lambda: q.settings
    app.dependency_overrides[current_user_model] = lambda: q.owner
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://isolated"
    ) as client:
        created = await client.post(
            "/api/v1/ai-quality-cases", json=q.request.model_dump(mode="json")
        )
        assert created.status_code == created.json()["code"] == 201
        assert created.headers["cache-control"] == "no-store"
        case_id = created.json()["data"]["id"]
        forbidden = await client.get("/api/v1/admin/ai-quality/cases/" + str(uuid4()))
        assert forbidden.status_code == 403 and forbidden.headers["cache-control"] == "no-store"
        app.dependency_overrides[current_user_model] = lambda: q.admin
        forbidden = await client.get("/api/v1/ai-quality-cases/" + case_id)
        assert forbidden.status_code == 403
        queue = await client.get("/api/v1/admin/ai-quality/cases")
        assert queue.status_code == 200 and "合成反馈" not in queue.text
        assert "description" not in queue.json()["data"][0]
        invalid = await client.post(
            "/api/v1/admin/ai-quality/cases/" + case_id + "/assign", json={"expected_version": 0}
        )
        assert invalid.status_code == 422 and invalid.headers["cache-control"] == "no-store"
        app.dependency_overrides[current_user_model] = lambda: q.owner
        original = created.json()["data"]
        grant = original["grants"][0]
        revoked = await client.request(
            "DELETE",
            f"/api/v1/ai-quality-cases/{case_id}/grants/{grant['id']}",
            json={
                "expected_version": original["version"],
                "expected_grant_version": grant["version"],
            },
        )
        assert revoked.status_code == revoked.json()["code"] == 200
        assert revoked.json()["data"]["grants"][0]["status"] == "revoked"
        assert revoked.headers["cache-control"] == "no-store"


async def test_snapshot_read_and_revoke_are_serialized_by_case_and_grant_locks(quality):
    q = quality
    created = await q.user.create(q.request)
    grant = created.grants[0]
    entered, release = asyncio.Event(), asyncio.Event()
    original = q.operator._source

    async def paused_source(session, case):
        result = await original(session, case)
        entered.set()
        await release.wait()
        return result

    q.operator._source = paused_source
    reading = asyncio.create_task(q.operator.snapshot(created.id, snapshot_request(grant)))
    await asyncio.wait_for(entered.wait(), 3)
    revoking = asyncio.create_task(
        q.user.grant_revoke(
            created.id,
            grant.id,
            GrantRevoke(expected_version=created.version, expected_grant_version=grant.version),
        )
    )
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(asyncio.shield(revoking), 0.05)
    release.set()
    assert (await asyncio.wait_for(reading, 3)).values["query"]
    revoked = await asyncio.wait_for(revoking, 3)
    q.operator._source = original
    with pytest.raises(ForbiddenError):
        await q.operator.snapshot(created.id, snapshot_request(revoked.grants[0]))


async def test_source_version_change_waits_for_authorized_read_then_denies_next_read(quality):
    q = quality
    created = await q.user.create(q.request)
    entered, release = asyncio.Event(), asyncio.Event()
    original = q.operator._source

    async def paused_source(session, case):
        source = await original(session, case)
        entered.set()
        await release.wait()
        return source

    async def retire():
        async with q.sessions.begin() as session:
            source = await session.scalar(
                select(DocumentProcessingVersion)
                .where(DocumentProcessingVersion.id == q.version_id)
                .with_for_update()
            )
            source.status = "retired"

    q.operator._source = paused_source
    reading = asyncio.create_task(
        q.operator.snapshot(created.id, snapshot_request(created.grants[0]))
    )
    await asyncio.wait_for(entered.wait(), 3)
    changing = asyncio.create_task(retire())
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(asyncio.shield(changing), 0.05)
    release.set()
    assert (await asyncio.wait_for(reading, 3)).values["query"]
    await asyncio.wait_for(changing, 3)
    q.operator._source = original
    with pytest.raises(ConflictError) as raised:
        await q.operator.snapshot(created.id, snapshot_request(created.grants[0]))
    assert raised.value.error_key == "SOURCE_UNAVAILABLE"


async def test_real_retention_grace_deleted_owner_and_anonymous_audits(quality):
    q = quality
    created = await q.user.create(q.request)
    grant = created.grants[0]
    revoked = await q.user.grant_revoke(
        created.id,
        grant.id,
        GrantRevoke(expected_version=created.version, expected_grant_version=grant.version),
    )
    revoked_at = revoked.grants[0].revoked_at
    async with q.sessions.begin() as session:
        await maintain_quality(session, q.settings, revoked_at + timedelta(days=6))
        assert await session.scalar(
            select(DiagnosticSnapshot).where(DiagnosticSnapshot.grant_id == grant.id)
        )
    async with q.sessions.begin() as session:
        await maintain_quality(session, q.settings, revoked_at + timedelta(days=7))
        assert (
            await session.scalar(
                select(DiagnosticSnapshot).where(DiagnosticSnapshot.grant_id == grant.id)
            )
            is None
        )
        case = await session.get(AIQualityCase, created.id)
        assert case.statement_ciphertext is None
    async with q.sessions.begin() as session:
        owner = await session.get(User, q.owner.id)
        owner.deleted_at = datetime.now(UTC)
        # 保存删除前新产生的安全事实；维护必须保留事件但断开身份和请求关联。
        audit = DiagnosticAudit(
            id=uuid4(),
            actor_id=q.admin.id,
            case_id=created.id,
            action="synthetic_delete",
            outcome="allowed",
            reason_code=None,
            fields=[],
            version=None,
            request_id="synthetic-request",
            occurred_at=datetime.now(UTC),
        )
        session.add(audit)
        audit_id = audit.id
    async with q.sessions.begin() as session:
        await maintain_quality(session, q.settings)
        assert await session.get(AIQualityCase, created.id) is None
        retained = await session.get(DiagnosticAudit, audit_id)
        assert (
            retained
            and retained.case_id is None
            and retained.actor_id is None
            and retained.request_id is None
        )


async def test_expiry_and_resolved_confirmation_deadline_deny_before_maintenance(quality):
    q = quality
    created = await q.user.create(q.request)
    assigned = await q.operator.assign(
        created.id, AssignmentRequest(expected_version=created.version)
    )
    resolved = await q.operator.transition(
        created.id,
        TransitionRequest(
            expected_version=assigned.version,
            status="resolved",
            resolution_code="not_reproduced",
            resolution_summary="合成确认期测试",
        ),
    )
    assert resolved.status == "resolved"
    async with q.sessions.begin() as session:
        case = await session.get(AIQualityCase, created.id)
        case.resolved_at = datetime.now(UTC) - timedelta(
            days=q.settings.ai_quality_confirmation_days + 1
        )
    with pytest.raises(ForbiddenError):
        await q.operator.snapshot(created.id, snapshot_request(created.grants[0]))
    hidden = await q.operator.admin_detail(created.id)
    assert all(event.content is None for event in hidden.events)
    async with q.sessions.begin() as session:
        await maintain_quality(session, q.settings)
        case = await session.get(AIQualityCase, created.id)
        assert case.status == "closed"
    another = await q.user.create(q.request.model_copy(update={"request_key": uuid4()}))
    async with q.sessions.begin() as session:
        grant = await session.get(DiagnosticAccessGrant, another.grants[0].id)
        grant.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(ForbiddenError):
        await q.operator.snapshot(another.id, snapshot_request(another.grants[0]))


@pytest.mark.parametrize(
    "change,error_key", [("strategy", "STRATEGY_UNAVAILABLE"), ("source", "SOURCE_UNAVAILABLE")]
)
async def test_failed_replay_persists_bodyless_record_and_returns_real_error(
    quality, change, error_key
):
    q = quality
    created = await q.user.create(q.request)
    assigned = await q.operator.assign(
        created.id, AssignmentRequest(expected_version=created.version)
    )
    async with q.sessions.begin() as session:
        if change == "strategy":
            trace = await session.get(RetrievalTrace, q.trace_id)
            trace.strategy_version = "unknown-future-strategy"
        else:
            version = await session.get(DocumentProcessingVersion, q.version_id)
            version.status = "retired"
    with pytest.raises(AppError) as raised:
        await q.operator.replay(
            created.id,
            ReplayRequest(
                expected_version=assigned.version,
                grant_id=created.grants[0].id,
                expected_grant_version=created.grants[0].version,
                mode="full",
            ),
        )
    assert raised.value.error_key == error_key
    detail = await q.operator.admin_detail(created.id)
    assert len(detail.replays) == 1
    assert detail.replays[0].status == "failed" and detail.replays[0].error_key == error_key
    assert detail.replays[0].ranking == [] and detail.replays[0].metrics["recall"] is None
    assert "Synthetic CedarQueue" not in detail.replays[0].model_dump_json()
    assert any(
        a.action == "replay_create" and a.outcome == "denied" and a.reason_code == error_key
        for a in detail.audits
    )


async def test_hourly_limit_is_configured_and_idempotent_retry_is_not_counted(quality):
    q = quality
    limited = QualityService(
        q.sessions, q.owner, q.settings.model_copy(update={"ai_quality_case_hourly_limit": 1})
    )
    first = await limited.create(q.request)
    assert (await limited.create(q.request)).id == first.id
    await limited.user_close(first.id, first.version)
    with pytest.raises(TooManyRequestsError) as raised:
        await limited.create(q.request.model_copy(update={"request_key": uuid4()}))
    assert raised.value.error_key == "QUALITY_RATE_LIMITED"


async def test_grants_cannot_cross_cases_and_rejected_request_never_reads_candidates(quality):
    q = quality
    first = await q.user.create(q.request)
    await q.user.user_close(first.id, first.version)
    second = await q.user.create(q.request.model_copy(update={"request_key": uuid4()}))
    with pytest.raises(NotFoundError):
        await q.operator.snapshot(second.id, snapshot_request(first.grants[0]))
    assigned = await q.operator.assign(
        second.id, AssignmentRequest(expected_version=second.version)
    )
    with pytest.raises(ForbiddenError):
        await q.operator.access_request(
            second.id,
            AccessRequest(
                expected_version=assigned.version, reason="合成超范围请求", chunk_ids=[uuid4()]
            ),
        )
    requested = await q.operator.access_request(
        second.id,
        AccessRequest(
            expected_version=assigned.version, reason="合成拒绝授权测试", chunk_ids=[q.chunk_id]
        ),
    )
    grant = next(g for g in requested.grants if "candidate_excerpts" in g.fields)
    rejected = await q.user.grant_decision(
        second.id,
        grant.id,
        GrantDecision(
            expected_version=requested.version, expected_grant_version=grant.version, approved=False
        ),
    )
    inactive = next(g for g in rejected.grants if g.id == grant.id)
    assert inactive.status == "rejected"
    with pytest.raises(ForbiddenError):
        await q.operator.snapshot(second.id, snapshot_request(inactive, ["candidate_excerpts"]))


async def test_180_day_metadata_cleanup_unlinks_recent_audit_and_removes_expired_audit(quality):
    q = quality
    created = await q.user.create(q.request)
    now = datetime.now(UTC)
    async with q.sessions.begin() as session:
        recent = DiagnosticAudit(
            id=uuid4(),
            actor_id=q.admin.id,
            case_id=created.id,
            action="synthetic_recent",
            outcome="allowed",
            reason_code=None,
            fields=[],
            version=1,
            request_id="synthetic",
            occurred_at=now + timedelta(days=180),
        )
        expired = DiagnosticAudit(
            id=uuid4(),
            actor_id=q.admin.id,
            case_id=created.id,
            action="synthetic_old",
            outcome="allowed",
            reason_code=None,
            fields=[],
            version=1,
            request_id="synthetic",
            occurred_at=now,
        )
        session.add_all([recent, expired])
        recent_id, expired_id = recent.id, expired.id
    async with q.sessions.begin() as session:
        await maintain_quality(session, q.settings, now + timedelta(days=181))
        assert await session.get(AIQualityCase, created.id) is None
        assert await session.get(DiagnosticAudit, expired_id) is None
        retained = await session.get(DiagnosticAudit, recent_id)
        assert (
            retained
            and retained.actor_id is None
            and retained.case_id is None
            and retained.request_id is None
        )
