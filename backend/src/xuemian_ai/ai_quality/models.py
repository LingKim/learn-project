"""正文只存加密载荷；列表、审计及回放表仅保存结构化元数据。"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from xuemian_ai.infrastructure.database import Base
from xuemian_ai.persistence.mixins import CreatedAtMixin, TimestampMixin, UuidPrimaryKeyMixin


class AIQualityCase(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_quality_cases"
    __table_args__ = (
        UniqueConstraint("user_id", "request_key", name="uq_quality_case_request"),
        UniqueConstraint("case_number", name="uq_quality_case_number"),
        Index(
            "uq_quality_active_source",
            "user_id",
            "source_type",
            "source_id",
            "trace_id",
            unique=True,
            postgresql_where=text("status <> 'closed'"),
        ),
        CheckConstraint("version >= 1", name="ck_quality_case_version"),
        CheckConstraint(
            "status IN ('submitted','triaging','waiting_user','investigating','resolved','closed')",
            name="ck_quality_case_status",
        ),
        Index("ix_quality_case_queue", "status", "created_at"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[UUID]
    trace_id: Mapped[UUID]
    knowledge_base_id: Mapped[UUID]
    case_number: Mapped[str] = mapped_column(String(48))
    request_key: Mapped[UUID]
    input_digest: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="submitted")
    version: Mapped[int] = mapped_column(Integer, default=1)
    assignee_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    strategy_version: Mapped[str] = mapped_column(String(128))
    trace_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB)
    statement_key_id: Mapped[str | None] = mapped_column(String(32))
    statement_ciphertext: Mapped[str | None] = mapped_column(Text)
    access_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_code: Mapped[str | None] = mapped_column(String(32))
    resolution_summary: Mapped[str | None] = mapped_column(Text)


class AIQualityCaseEvent(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "ai_quality_case_events"
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("ai_quality_cases.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(48))
    visibility: Mapped[str] = mapped_column(String(8))
    version: Mapped[int]
    key_id: Mapped[str | None] = mapped_column(String(32))
    ciphertext: Mapped[str | None] = mapped_column(Text)


class DiagnosticAccessGrant(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "diagnostic_access_grants"
    __table_args__ = (
        UniqueConstraint("id", "case_id", name="uq_quality_grant_case"),
        CheckConstraint("version >= 1", name="ck_quality_grant_version"),
        CheckConstraint(
            "status IN ('pending','active','expired','revoked','rejected')",
            name="ck_quality_grant_status",
        ),
        Index("ix_quality_grant_expiry", "status", "expires_at"),
    )
    case_id: Mapped[UUID] = mapped_column(ForeignKey("ai_quality_cases.id", ondelete="CASCADE"))
    requester_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    fields: Mapped[list[str]] = mapped_column(JSONB)
    chunk_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    reason: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    version: Mapped[int] = mapped_column(Integer, default=1)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DiagnosticSnapshot(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "diagnostic_snapshots"
    __table_args__ = (UniqueConstraint("grant_id", name="uq_quality_snapshot_grant"),)
    grant_id: Mapped[UUID] = mapped_column(
        ForeignKey("diagnostic_access_grants.id", ondelete="CASCADE")
    )
    key_id: Mapped[str] = mapped_column(String(32))
    ciphertext: Mapped[str] = mapped_column(Text)


class DiagnosticReplay(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "diagnostic_replays"
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("ai_quality_cases.id", ondelete="CASCADE"), index=True
    )
    grant_id: Mapped[UUID] = mapped_column(
        ForeignKey("diagnostic_access_grants.id", ondelete="CASCADE")
    )
    grant_version: Mapped[int]
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    mode: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(16))
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    error_key: Mapped[str | None] = mapped_column(String(64))


class DiagnosticAudit(UuidPrimaryKeyMixin, Base):
    __tablename__ = "diagnostic_audits"
    __table_args__ = (Index("ix_quality_audit_expiry", "occurred_at"),)
    # 不建业务对象外键：清理工单后只留下无法反查正文的安全事实。
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    case_id: Mapped[UUID | None]
    action: Mapped[str] = mapped_column(String(48))
    outcome: Mapped[str] = mapped_column(String(16))
    reason_code: Mapped[str | None] = mapped_column(String(64))
    fields: Mapped[list[str]] = mapped_column(JSONB, default=list)
    version: Mapped[int | None]
    request_id: Mapped[str | None] = mapped_column(String(128))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
