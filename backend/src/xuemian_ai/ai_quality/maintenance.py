"""定时维护授权生命周期；只保留无正文事实，不解密或复制任何业务正文。"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xuemian_ai.accounts.models import User
from xuemian_ai.ai_quality.models import (
    AIQualityCase,
    AIQualityCaseEvent,
    DiagnosticAccessGrant,
    DiagnosticAudit,
    DiagnosticSnapshot,
)
from xuemian_ai.document_processing.models import RetrievalTrace

_GRACE = timedelta(days=7)
_RETENTION = timedelta(days=180)


def _record(session: AsyncSession, case: AIQualityCase, action: str, now: datetime) -> None:
    # 系统动作没有操作者、请求标识或正文载荷，避免后台任务制造敏感副本。
    session.add(
        AIQualityCaseEvent(
            id=uuid4(),
            case_id=case.id,
            actor_id=None,
            action=action,
            visibility="user",
            version=case.version,
            created_at=now,
            key_id=None,
            ciphertext=None,
        )
    )
    session.add(
        DiagnosticAudit(
            id=uuid4(),
            actor_id=None,
            case_id=case.id,
            action=action,
            outcome="allowed",
            reason_code=None,
            fields=[],
            version=case.version,
            request_id=None,
            occurred_at=now,
        )
    )


def _end_of_access(case: AIQualityCase, grant: DiagnosticAccessGrant) -> datetime:
    ends = [case.access_expires_at, grant.expires_at]
    if grant.revoked_at is not None:
        ends.append(grant.revoked_at)
    if case.closed_at is not None:
        ends.append(case.closed_at)
    return min(ends)


async def maintain_quality(
    session: AsyncSession, settings: Any, now: datetime | None = None
) -> dict[str, int]:
    """由 scheduler 的已有事务调用；不自行开启、提交或回滚事务。"""
    if not session.in_transaction():
        raise RuntimeError("quality maintenance requires an existing transaction")
    now = now or datetime.now(UTC)
    counts = dict.fromkeys(
        (
            "cases_closed",
            "grants_revoked",
            "grants_expired",
            "snapshots_deleted",
            "statements_cleared",
            "event_bodies_cleared",
            "cases_deleted",
            "audits_anonymized",
            "audits_deleted",
            "traces_updated",
            "traces_deleted",
            "trace_metadata_cleared",
        ),
        0,
    )
    # 与用户读取/撤销一致，先 Case 再 Grant；重载防止 Session 缓存旧授权状态。
    cases = list(
        (
            await session.scalars(
                select(AIQualityCase)
                .order_by(AIQualityCase.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    surviving: list[AIQualityCase] = []
    removed_cases: list[AIQualityCase] = []
    removed_case_ids: set[UUID] = set()
    deleted_owner_ids: set[UUID] = set()
    for case in cases:
        grants = list(
            (
                await session.scalars(
                    select(DiagnosticAccessGrant)
                    .where(DiagnosticAccessGrant.case_id == case.id)
                    .order_by(DiagnosticAccessGrant.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        owner = await session.get(User, case.user_id, populate_existing=True)
        owner_deleted = owner is None or owner.deleted_at is not None
        if owner_deleted:
            deleted_owner_ids.add(case.user_id)
        if (
            not owner_deleted
            and case.status == "resolved"
            and case.resolved_at is not None
            and case.resolved_at + timedelta(days=settings.ai_quality_confirmation_days) <= now
        ):
            case.status = "closed"
            # 迟跑任务不延长用户已经结束的访问期限和正文清理宽限期。
            case.closed_at = case.resolved_at + timedelta(
                days=settings.ai_quality_confirmation_days
            )
            case.version += 1
            counts["cases_closed"] += 1
            _record(session, case, "case_auto_closed", now)
        for grant in grants:
            if grant.status in {"active", "pending"}:
                if owner_deleted or case.status == "closed":
                    grant.status = "revoked"
                    grant.revoked_at = now if owner_deleted else (case.closed_at or now)
                    grant.version += 1
                    counts["grants_revoked"] += 1
                    _record(session, case, "grant_auto_revoked", now)
                elif min(grant.expires_at, case.access_expires_at) <= now:
                    grant.status = "expired"
                    grant.version += 1
                    case.version += 1
                    counts["grants_expired"] += 1
                    _record(session, case, "grant_auto_expired", now)
            if owner_deleted or _end_of_access(case, grant) + _GRACE <= now:
                for snapshot in (
                    await session.scalars(
                        select(DiagnosticSnapshot).where(DiagnosticSnapshot.grant_id == grant.id)
                    )
                ).all():
                    await session.delete(snapshot)
                    counts["snapshots_deleted"] += 1
        # 所有工单正文共享基础授权；追加候选授权不能续期描述或内部备注。
        statement_ends = [case.access_expires_at]
        statement_ends.extend(
            _end_of_access(case, grant) for grant in grants if "query" in grant.fields
        )
        if case.closed_at is not None:
            statement_ends.append(case.closed_at)
        if owner_deleted or min(statement_ends) + _GRACE <= now:
            if case.statement_ciphertext is not None or case.statement_key_id is not None:
                case.statement_ciphertext = case.statement_key_id = None
                counts["statements_cleared"] += 1
            for event in (
                await session.scalars(
                    select(AIQualityCaseEvent).where(AIQualityCaseEvent.case_id == case.id)
                )
            ).all():
                if event.ciphertext is not None or event.key_id is not None:
                    event.ciphertext = event.key_id = None
                    counts["event_bodies_cleared"] += 1
        if owner_deleted or case.created_at + _RETENTION <= now:
            removed_case_ids.add(case.id)
            removed_cases.append(case)
            counts["cases_deleted"] += 1
        else:
            surviving.append(case)
    # 用户可能已经物理删除，工单级联后仅剩无外键审计：一并断开反查链。
    live_case_ids = {case.id for case in surviving}
    audits = list((await session.scalars(select(DiagnosticAudit))).all())
    for audit in audits:
        if audit.occurred_at + _RETENTION <= now:
            await session.delete(audit)
            counts["audits_deleted"] += 1
            continue
        orphaned = audit.case_id is not None and audit.case_id not in live_case_ids
        actor = (
            await session.get(User, audit.actor_id, populate_existing=True)
            if audit.actor_id is not None
            else None
        )
        deleted_actor = audit.actor_id is not None and (
            actor is None or actor.deleted_at is not None
        )
        # 物理删除会 SET NULL 操作者；已无身份/工单的 request_id 也不再保留。
        unlinked_request = audit.actor_id is None and audit.case_id is None
        if (
            orphaned
            or audit.case_id in removed_case_ids
            or audit.actor_id in deleted_owner_ids
            or deleted_actor
            or unlinked_request
        ):
            if any(
                value is not None for value in (audit.case_id, audit.actor_id, audit.request_id)
            ):
                audit.case_id = audit.actor_id = audit.request_id = None
                counts["audits_anonymized"] += 1
    if removed_cases:
        # 先落盘匿名审计，再删除来源身份；业务子表由已定义外键级联清理。
        await session.flush()
        for case in removed_cases:
            await session.delete(case)
    by_trace: dict[UUID, list[AIQualityCase]] = {}
    for case in surviving:
        by_trace.setdefault(case.trace_id, []).append(case)
    # Case/Grant 锁在前，Trace 锁在后；多个工单不能被最后关闭者缩短保留期。
    traces = list(
        (
            await session.scalars(
                select(RetrievalTrace)
                .order_by(RetrievalTrace.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    available_trace_ids = {trace.id for trace in traces}
    for trace in traces:
        trace_owner = await session.get(User, trace.user_id, populate_existing=True)
        owner_unavailable = trace_owner is None or trace_owner.deleted_at is not None
        references = by_trace.get(trace.id, [])
        upper = trace.occurred_at + _RETENTION
        expires = max(
            (
                min(upper, case.closed_at + timedelta(days=90))
                if case.closed_at is not None
                else upper
                for case in references
            ),
            default=min(upper, trace.occurred_at + timedelta(days=30)),
        )
        if owner_unavailable or trace.user_id in deleted_owner_ids or expires <= now:
            await session.delete(trace)
            counts["traces_deleted"] += 1
            for case in references:
                if case.trace_metadata:
                    case.trace_metadata = {}
                    counts["trace_metadata_cleared"] += 1
        elif trace.expires_at != expires or trace.retained_by_case != bool(references):
            trace.expires_at = expires
            trace.retained_by_case = bool(references)
            counts["traces_updated"] += 1
    # 物理删除 Trace 后，工单里的元数据副本也必须停止保留，不能绕过期限。
    for case in surviving:
        if case.trace_id not in available_trace_ids and case.trace_metadata:
            case.trace_metadata = {}
            counts["trace_metadata_cleared"] += 1
    await session.flush()
    return counts
