from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from xuemian_ai.accounts.models import User
from xuemian_ai.ai_quality.maintenance import maintain_quality
from xuemian_ai.ai_quality.models import (
    AIQualityCase,
    AIQualityCaseEvent,
    DiagnosticAccessGrant,
    DiagnosticAudit,
    DiagnosticReplay,
    DiagnosticSnapshot,
)
from xuemian_ai.document_processing.models import RetrievalTrace

NOW = datetime(2026, 10, 3, 12, tzinfo=UTC)
SETTINGS = SimpleNamespace(ai_quality_confirmation_days=7)


class Rows:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def all(self) -> list[Any]:
        return list(self.rows)


class MemorySession:
    """只模拟行读写和已定义 FK 级联，时间与状态规则均由被测实现决定。"""

    def __init__(self, objects: list[Any]) -> None:
        self.objects = objects
        self.statements: list[Any] = []
        self.transaction = True

    def in_transaction(self) -> bool:
        return self.transaction

    async def scalars(self, statement: Any) -> Rows:
        self.statements.append(statement)
        model = statement.column_descriptions[0]["entity"]
        rows = [item for item in self.objects if type(item) is model]
        params = list(statement.compile().params.values())
        if params:
            attribute = "grant_id" if model is DiagnosticSnapshot else "case_id"
            rows = [item for item in rows if getattr(item, attribute) == params[0]]
        return Rows(rows)

    async def get(self, model: Any, key: UUID, **kwargs: Any) -> Any:
        return next((row for row in self.objects if type(row) is model and row.id == key), None)

    def add(self, item: Any) -> None:
        self.objects.append(item)

    async def delete(self, item: Any) -> None:
        if item not in self.objects:
            return
        self.objects.remove(item)
        if isinstance(item, AIQualityCase):
            for row in list(self.objects):
                if isinstance(row, (AIQualityCaseEvent, DiagnosticAccessGrant, DiagnosticReplay)):
                    if row.case_id == item.id:
                        await self.delete(row)
        elif isinstance(item, DiagnosticAccessGrant):
            for row in list(self.objects):
                if (
                    isinstance(row, (DiagnosticSnapshot, DiagnosticReplay))
                    and row.grant_id == item.id
                ):
                    await self.delete(row)

    async def flush(self) -> None:
        pass

    def rows(self, model: Any) -> list[Any]:
        return [row for row in self.objects if type(row) is model]


def fixture() -> tuple[MemorySession, AIQualityCase, DiagnosticAccessGrant, RetrievalTrace, User]:
    user = User(id=uuid4(), deleted_at=None)
    trace = RetrievalTrace(
        id=uuid4(),
        user_id=user.id,
        occurred_at=NOW - timedelta(days=10),
        expires_at=NOW + timedelta(days=170),
        retained_by_case=True,
    )
    case = AIQualityCase(
        id=uuid4(),
        user_id=user.id,
        trace_id=trace.id,
        status="submitted",
        version=1,
        created_at=NOW - timedelta(days=10),
        access_expires_at=NOW + timedelta(days=20),
        statement_key_id="synthetic",
        statement_ciphertext="encrypted synthetic statement",
        trace_metadata={"strategy_version": "synthetic"},
        resolved_at=None,
        closed_at=None,
    )
    grant = DiagnosticAccessGrant(
        id=uuid4(),
        case_id=case.id,
        status="active",
        version=1,
        fields=["query", "final_output", "final_citations"],
        expires_at=case.access_expires_at,
        revoked_at=None,
    )
    snapshot = DiagnosticSnapshot(
        id=uuid4(), grant_id=grant.id, key_id="synthetic", ciphertext="cipher"
    )
    event = AIQualityCaseEvent(
        id=uuid4(),
        case_id=case.id,
        action="case_created",
        actor_id=user.id,
        created_at=case.created_at,
        visibility="user",
        version=1,
        key_id="synthetic",
        ciphertext="cipher",
    )
    audit = DiagnosticAudit(
        id=uuid4(),
        case_id=case.id,
        actor_id=user.id,
        occurred_at=NOW,
        request_id="synthetic request",
        action="snapshot_read",
        outcome="allowed",
        fields=[],
    )
    replay = DiagnosticReplay(id=uuid4(), case_id=case.id, grant_id=grant.id, result={})
    return (
        MemorySession([user, trace, case, grant, snapshot, event, audit, replay]),
        case,
        grant,
        trace,
        user,
    )


async def run(session: MemorySession, now: datetime = NOW) -> dict[str, int]:
    return await maintain_quality(cast(AsyncSession, session), SETTINGS, now)


async def test_resolved_confirmation_boundary_closes_and_revokes_without_body_events() -> None:
    session, case, grant, trace, _ = fixture()
    case.status, case.resolved_at = "resolved", NOW - timedelta(days=7)
    pending = DiagnosticAccessGrant(
        id=uuid4(),
        case_id=case.id,
        status="pending",
        version=2,
        expires_at=NOW + timedelta(days=1),
        fields=["candidate_excerpts"],
        revoked_at=None,
    )
    session.add(pending)
    assert (await run(session, NOW - timedelta(microseconds=1)))["cases_closed"] == 0
    counts = await run(session)
    assert counts["cases_closed"] == 1
    assert counts["grants_revoked"] == 2
    assert case.status == "closed" and case.closed_at == NOW and case.version == 2
    assert grant.status == pending.status == "revoked"
    assert grant.version == 2 and pending.version == 3
    assert grant.revoked_at == pending.revoked_at == NOW
    assert trace.expires_at == NOW + timedelta(days=90)
    for model in (AIQualityCaseEvent, DiagnosticAudit):
        generated = [
            row for row in session.rows(model) if row.action.endswith(("closed", "revoked"))
        ]
        assert len(generated) == 3
        assert all(row.actor_id is None for row in generated)
        if model is AIQualityCaseEvent:
            assert all(row.key_id is None and row.ciphertext is None for row in generated)
        else:
            assert all(row.request_id is None and row.fields == [] for row in generated)
    assert all(value == 0 for value in (await run(session)).values())


async def test_delayed_automatic_close_does_not_extend_seven_day_cleanup_grace() -> None:
    session, case, grant, _, _ = fixture()
    case.status, case.resolved_at = "resolved", NOW - timedelta(days=14)
    counts = await run(session)
    assert case.closed_at == grant.revoked_at == NOW - timedelta(days=7)
    assert counts["snapshots_deleted"] == 1
    assert counts["statements_cleared"] == counts["event_bodies_cleared"] == 1
    assert case.statement_ciphertext is case.statement_key_id is None
    assert session.rows(DiagnosticSnapshot) == []


@pytest.mark.parametrize("end", ["expires_at", "revoked_at", "closed_at"])
async def test_snapshot_and_all_case_body_cleanup_uses_earliest_end_at_exact_boundary(
    end: str,
) -> None:
    session, case, grant, _, _ = fixture()
    cutoff = NOW - timedelta(days=7)
    if end == "expires_at":
        grant.expires_at = cutoff
    elif end == "revoked_at":
        grant.status, grant.revoked_at = "revoked", cutoff
    else:
        case.status, case.closed_at = "closed", cutoff
    counts = await run(session, NOW - timedelta(microseconds=1))
    assert counts["snapshots_deleted"] == counts["statements_cleared"] == 0
    counts = await run(session)
    assert counts["snapshots_deleted"] == counts["statements_cleared"] == 1
    assert counts["event_bodies_cleared"] == 1
    assert all(value == 0 for value in (await run(session)).values())


async def test_only_additional_grant_revocation_does_not_purge_base_statement() -> None:
    session, case, _, _, _ = fixture()
    additional = DiagnosticAccessGrant(
        id=uuid4(),
        case_id=case.id,
        fields=["candidate_excerpts"],
        status="revoked",
        version=2,
        expires_at=NOW + timedelta(days=10),
        revoked_at=NOW - timedelta(days=7),
    )
    session.add(additional)
    session.add(
        DiagnosticSnapshot(id=uuid4(), grant_id=additional.id, ciphertext="cipher", key_id="key")
    )
    counts = await run(session)
    assert counts["snapshots_deleted"] == 1
    assert counts["statements_cleared"] == counts["event_bodies_cleared"] == 0
    assert case.statement_ciphertext is not None


async def test_active_and_pending_grants_expire_and_increment_versions_once() -> None:
    session, case, grant, _, _ = fixture()
    case.access_expires_at = NOW
    pending = DiagnosticAccessGrant(
        id=uuid4(),
        case_id=case.id,
        status="pending",
        version=3,
        expires_at=NOW + timedelta(days=10),
        fields=["candidate_excerpts"],
        revoked_at=None,
    )
    session.add(pending)
    assert (await run(session, NOW - timedelta(microseconds=1)))["grants_expired"] == 0
    counts = await run(session)
    assert counts["grants_expired"] == 2
    assert grant.status == pending.status == "expired"
    assert grant.version == 2 and pending.version == 4 and case.version == 3
    assert counts["snapshots_deleted"] == counts["statements_cleared"] == 0
    assert all(value == 0 for value in (await run(session)).values())


@pytest.mark.parametrize("removed", [False, True])
async def test_owner_deletion_immediately_purges_bodies_and_anonymizes_audit(removed: bool) -> None:
    session, case, grant, trace, owner = fixture()
    if removed:
        session.objects.remove(owner)
    else:
        owner.deleted_at = NOW
    counts = await run(session)
    assert counts["grants_revoked"] == counts["snapshots_deleted"] == 1
    assert counts["cases_deleted"] == counts["traces_deleted"] == 1
    assert counts["statements_cleared"] == counts["event_bodies_cleared"] == 1
    assert grant.status == "revoked"
    assert session.rows(AIQualityCase) == session.rows(DiagnosticAccessGrant) == []
    assert session.rows(AIQualityCaseEvent) == session.rows(DiagnosticSnapshot) == []
    assert session.rows(DiagnosticReplay) == []
    assert session.rows(RetrievalTrace) == []
    assert case not in session.objects and trace not in session.objects
    assert all(
        a.case_id is a.actor_id is a.request_id is None for a in session.rows(DiagnosticAudit)
    )
    assert all(value == 0 for value in (await run(session)).values())


async def test_case_180_day_retention_anonymizes_recent_audit_but_deletes_old_audit() -> None:
    session, case, _, trace, _ = fixture()
    case.created_at = NOW - timedelta(days=180)
    trace.occurred_at = case.created_at
    old = DiagnosticAudit(
        id=uuid4(),
        case_id=case.id,
        actor_id=case.user_id,
        request_id="old",
        occurred_at=NOW - timedelta(days=180),
    )
    session.add(old)
    counts = await run(session)
    assert counts["cases_deleted"] == counts["audits_deleted"] == counts["traces_deleted"] == 1
    assert old not in session.objects
    assert counts["audits_anonymized"] == 1
    assert all(
        a.case_id is a.actor_id is a.request_id is None for a in session.rows(DiagnosticAudit)
    )


async def test_orphan_audit_after_physical_case_cascade_is_anonymous() -> None:
    session, case, _, _, _ = fixture()
    await session.delete(case)
    counts = await run(session)
    assert counts["audits_anonymized"] == 1
    assert all(
        a.case_id is a.actor_id is a.request_id is None for a in session.rows(DiagnosticAudit)
    )


async def test_multiple_cases_share_trace_longest_valid_retention_and_total_cap() -> None:
    session, case, _, trace, _ = fixture()
    case.status, case.closed_at = "closed", NOW - timedelta(days=1)
    second = AIQualityCase(
        id=uuid4(),
        user_id=case.user_id,
        trace_id=trace.id,
        status="submitted",
        version=1,
        created_at=NOW,
        access_expires_at=NOW + timedelta(days=30),
        trace_metadata={},
        statement_ciphertext=None,
        statement_key_id=None,
    )
    session.add(second)
    trace.expires_at = NOW + timedelta(days=89)
    await run(session)
    assert trace.expires_at == trace.occurred_at + timedelta(days=180)
    second.status, second.closed_at = "closed", NOW
    await run(session)
    assert trace.expires_at == NOW + timedelta(days=90)
    trace.occurred_at = NOW - timedelta(days=180)
    counts = await run(session)
    assert counts["traces_deleted"] == counts["trace_metadata_cleared"] == 1
    assert case.trace_metadata == {}


async def test_ordinary_unbound_trace_expires_at_thirty_days() -> None:
    session, case, _, trace, _ = fixture()
    await session.delete(case)
    trace.occurred_at = NOW - timedelta(days=30)
    assert (await run(session))["traces_deleted"] == 1


async def test_missing_trace_drops_case_metadata_copy() -> None:
    session, case, _, trace, _ = fixture()
    session.objects.remove(trace)
    assert (await run(session))["trace_metadata_cleared"] == 1
    assert case.trace_metadata == {}


async def test_deleted_trace_owner_without_any_case_is_still_purged() -> None:
    session, case, _, _, owner = fixture()
    await session.delete(case)
    owner.deleted_at = NOW
    assert (await run(session))["traces_deleted"] == 1


async def test_lock_order_case_then_grants_and_transaction_is_caller_owned() -> None:
    session, _, _, _, _ = fixture()
    session.transaction = False
    with pytest.raises(RuntimeError, match="existing transaction"):
        await run(session)
    assert session.statements == []
    session.transaction = True
    await run(session)
    assert session.statements[0].column_descriptions[0]["entity"] is AIQualityCase
    assert session.statements[1].column_descriptions[0]["entity"] is DiagnosticAccessGrant
    for statement in session.statements[:2]:
        assert statement._for_update_arg is not None
        assert statement.get_execution_options()["populate_existing"] is True
