from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from xuemian_ai.infrastructure.database import Base
from xuemian_ai.persistence.mixins import (
    ActorAuditMixin,
    CreatedAtMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UuidPrimaryKeyMixin,
)
from xuemian_ai.practice.models import OwnerMixin


class Weakness(
    UuidPrimaryKeyMixin, TimestampMixin, ActorAuditMixin, SoftDeleteMixin, OwnerMixin, Base
):
    __tablename__ = "learning_weaknesses"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "request_key", name="uq_learning_weakness_request"),
        UniqueConstraint("id", "owner_user_id", name="uq_learning_weakness_owner"),
        Index(
            "uq_learning_weakness_active",
            "owner_user_id",
            "source_scope_key",
            "concept_key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint("version >= 1", name="ck_learning_weakness_version"),
        CheckConstraint(
            "decision IN ('pending','confirmed','ignored','revoked')",
            name="ck_learning_weakness_decision",
        ),
        CheckConstraint(
            "mastery_state IN ('to_learn','learning','to_verify','mastered')",
            name="ck_learning_weakness_mastery",
        ),
    )
    title: Mapped[str] = mapped_column(String(120))
    concept_key: Mapped[str] = mapped_column(String(500))
    source_scope_key: Mapped[str] = mapped_column(String(64))
    source_config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    source_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    domain: Mapped[str | None] = mapped_column(String(120))
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    decision: Mapped[str] = mapped_column(String(16), default="pending")
    mastery_state: Mapped[str] = mapped_column(String(16), default="to_learn")
    version: Mapped[int] = mapped_column(Integer, default=1)
    evidence_sufficient: Mapped[bool] = mapped_column(Boolean, default=False)
    policy_version: Mapped[str] = mapped_column(String(64), default="practice_weakness_v1")
    request_key: Mapped[UUID | None]
    input_digest: Mapped[str | None] = mapped_column(String(64))
    explanation_id: Mapped[UUID | None]
    last_user_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    blocked_question_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)


class WeaknessEvidence(UuidPrimaryKeyMixin, CreatedAtMixin, OwnerMixin, Base):
    __tablename__ = "learning_weakness_evidence"
    __table_args__ = (
        UniqueConstraint("weakness_id", "source_key", name="uq_learning_evidence_source"),
        ForeignKeyConstraint(
            ["weakness_id", "owner_user_id"],
            ["learning_weaknesses.id", "learning_weaknesses.owner_user_id"],
            name="fk_learning_evidence_owner",
            ondelete="CASCADE",
        ),
    )
    weakness_id: Mapped[UUID]
    kind: Mapped[str] = mapped_column(String(16))
    source_key: Mapped[str] = mapped_column(String(200))
    question_id: Mapped[UUID | None]
    attempt_id: Mapped[UUID | None]
    revision_id: Mapped[UUID | None]
    submission_id: Mapped[UUID | None]
    grade_id: Mapped[UUID | None]
    grade_version: Mapped[int | None]
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB)
    superseded: Mapped[bool] = mapped_column(Boolean, default=False)
    ignored: Mapped[bool] = mapped_column(Boolean, default=False)
    policy_version: Mapped[str] = mapped_column(String(64), default="practice_weakness_v1")


class WeaknessEvent(UuidPrimaryKeyMixin, CreatedAtMixin, OwnerMixin, Base):
    __tablename__ = "learning_weakness_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["weakness_id", "owner_user_id"],
            ["learning_weaknesses.id", "learning_weaknesses.owner_user_id"],
            name="fk_learning_event_owner",
            ondelete="CASCADE",
        ),
    )
    weakness_id: Mapped[UUID]
    event_type: Mapped[str] = mapped_column(String(40))
    version: Mapped[int] = mapped_column(Integer)
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    request_key: Mapped[UUID | None]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class LearningEvidenceEvent(UuidPrimaryKeyMixin, CreatedAtMixin, OwnerMixin, Base):
    __tablename__ = "learning_evidence_outbox"
    __table_args__ = (
        UniqueConstraint(
            "event_type", "object_id", "object_version", name="uq_learning_outbox_event"
        ),
        Index("ix_learning_outbox_due", "processed_at", "created_at"),
    )
    event_type: Mapped[str] = mapped_column(String(32))
    object_id: Mapped[UUID]
    object_version: Mapped[int] = mapped_column(Integer)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeExplanation(
    UuidPrimaryKeyMixin, TimestampMixin, ActorAuditMixin, SoftDeleteMixin, OwnerMixin, Base
):
    __tablename__ = "learning_explanations"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "request_key", name="uq_learning_explanation_request"),
        UniqueConstraint("id", "owner_user_id", name="uq_learning_explanation_owner"),
        ForeignKeyConstraint(
            ["weakness_id", "owner_user_id"],
            ["learning_weaknesses.id", "learning_weaknesses.owner_user_id"],
            name="fk_learning_explanation_owner",
            ondelete="CASCADE",
        ),
    )
    weakness_id: Mapped[UUID | None]
    topic: Mapped[str] = mapped_column(String(500))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    effective_context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    source_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    active_card_version: Mapped[int | None]
    request_key: Mapped[UUID]
    input_digest: Mapped[str] = mapped_column(String(64))


class KnowledgeCardVersion(UuidPrimaryKeyMixin, CreatedAtMixin, OwnerMixin, Base):
    __tablename__ = "learning_knowledge_cards"
    __table_args__ = (
        UniqueConstraint("explanation_id", "version", name="uq_learning_card_version"),
        ForeignKeyConstraint(
            ["explanation_id", "owner_user_id"],
            ["learning_explanations.id", "learning_explanations.owner_user_id"],
            name="fk_learning_card_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["run_id", "owner_user_id"],
            ["learning_knowledge_runs.id", "learning_knowledge_runs.owner_user_id"],
            name="fk_learning_card_run_owner",
            ondelete="CASCADE",
        ),
    )
    explanation_id: Mapped[UUID]
    version: Mapped[int] = mapped_column(Integer)
    parent_version: Mapped[int | None]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    source_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    run_id: Mapped[UUID]


class KnowledgeRun(UuidPrimaryKeyMixin, TimestampMixin, OwnerMixin, Base):
    __tablename__ = "learning_knowledge_runs"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "request_key", name="uq_learning_run_key"),
        UniqueConstraint("id", "owner_user_id", name="uq_learning_run_owner"),
        ForeignKeyConstraint(
            ["explanation_id", "owner_user_id"],
            ["learning_explanations.id", "learning_explanations.owner_user_id"],
            name="fk_learning_run_owner",
            ondelete="CASCADE",
        ),
        Index("ix_learning_runs_due", "status", "created_at"),
        CheckConstraint(
            "status IN ('pending','processing','cancel_requested',"
            "'succeeded','failed','cancelled')",
            name="ck_learning_run_status",
        ),
    )
    explanation_id: Mapped[UUID]
    operation: Mapped[str] = mapped_column(String(24))
    expected_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    stage: Mapped[str] = mapped_column(String(32), default="waiting")
    request_key: Mapped[UUID]
    input_digest: Mapped[str] = mapped_column(String(64))
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    result_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False)
    error_key: Mapped[str | None] = mapped_column(String(64))
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_token: Mapped[UUID | None]
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class LearningReview(UuidPrimaryKeyMixin, CreatedAtMixin, OwnerMixin, Base):
    __tablename__ = "learning_reviews"
    __table_args__ = (
        UniqueConstraint("attempt_id", "input_digest", name="uq_learning_review_input"),
        UniqueConstraint("attempt_id", "version", name="uq_learning_review_version"),
    )
    target_kind: Mapped[str] = mapped_column(String(16))
    target_id: Mapped[UUID]
    target_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    set_id: Mapped[UUID] = mapped_column(ForeignKey("practice_sets.id", ondelete="CASCADE"))
    attempt_id: Mapped[UUID] = mapped_column(ForeignKey("practice_attempts.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    input_digest: Mapped[str] = mapped_column(String(64))
    source_available: Mapped[bool] = mapped_column(Boolean)
    total_related: Mapped[int] = mapped_column(Integer)
    submitted_count: Mapped[int] = mapped_column(Integer)
    graded_count: Mapped[int] = mapped_column(Integer)
    correct_count: Mapped[int] = mapped_column(Integer)
    low_confidence_count: Mapped[int] = mapped_column(Integer)
    validation_passed: Mapped[bool] = mapped_column(Boolean)
    conclusion: Mapped[str] = mapped_column(String(64))
