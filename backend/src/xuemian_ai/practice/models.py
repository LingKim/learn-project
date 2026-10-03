from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
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


class OwnerMixin:
    owner_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )


class SetReferenceMixin:
    set_id: Mapped[UUID] = mapped_column(
        ForeignKey("practice_sets.id", ondelete="CASCADE"), nullable=False
    )


class PracticeSet(
    UuidPrimaryKeyMixin, TimestampMixin, ActorAuditMixin, SoftDeleteMixin, OwnerMixin, Base
):
    __tablename__ = "practice_sets"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "request_key", name="uq_practice_set_key"),
        Index("ix_practice_sets_owner", "owner_user_id", "created_at"),
        CheckConstraint("version >= 1", name="ck_practice_set_version"),
    )
    title: Mapped[str] = mapped_column(String(120))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    effective_context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    source_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    current_revision_id: Mapped[UUID | None]
    request_key: Mapped[UUID]
    input_digest: Mapped[str] = mapped_column(String(64))


class PracticePlan(UuidPrimaryKeyMixin, CreatedAtMixin, OwnerMixin, SetReferenceMixin, Base):
    __tablename__ = "practice_plans"
    __table_args__ = (UniqueConstraint("set_id", "version", name="uq_practice_plan_version"),)
    version: Mapped[int] = mapped_column(Integer)
    base_set_version: Mapped[int] = mapped_column(Integer)
    candidates: Mapped[dict[str, Any]] = mapped_column(JSONB)
    suggestions: Mapped[list[str]] = mapped_column(JSONB)
    input_digest: Mapped[str] = mapped_column(String(64))
    run_id: Mapped[UUID]


class PracticeRevision(UuidPrimaryKeyMixin, CreatedAtMixin, OwnerMixin, SetReferenceMixin, Base):
    __tablename__ = "practice_revisions"
    __table_args__ = (UniqueConstraint("set_id", "version", name="uq_practice_revision_version"),)
    version: Mapped[int] = mapped_column(Integer)
    parent_revision_id: Mapped[UUID | None]
    plan_id: Mapped[UUID | None]
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    effective_context: Mapped[dict[str, Any]] = mapped_column(JSONB)
    source_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    questions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(String(32))
    run_id: Mapped[UUID | None]
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class PracticeAttempt(
    UuidPrimaryKeyMixin, TimestampMixin, ActorAuditMixin, OwnerMixin, SetReferenceMixin, Base
):
    __tablename__ = "practice_attempts"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "request_key", name="uq_practice_attempt_key"),
        CheckConstraint("status IN ('active','completed')", name="ck_practice_attempt_status"),
    )
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("practice_revisions.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(16), default="active")
    version: Mapped[int] = mapped_column(Integer, default=1)
    current_question_id: Mapped[UUID | None]
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_key: Mapped[UUID]
    input_digest: Mapped[str] = mapped_column(String(64))


class PracticeAnswer(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "practice_answers"
    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", name="uq_practice_answer_question"),
    )
    attempt_id: Mapped[UUID] = mapped_column(ForeignKey("practice_attempts.id", ondelete="CASCADE"))
    question_id: Mapped[UUID]
    version: Mapped[int] = mapped_column(Integer, default=1)
    answer: Mapped[dict[str, Any]] = mapped_column(JSONB)


class PracticeSubmission(UuidPrimaryKeyMixin, CreatedAtMixin, OwnerMixin, Base):
    __tablename__ = "practice_submissions"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "request_key", name="uq_practice_submission_key"),
    )
    attempt_id: Mapped[UUID] = mapped_column(ForeignKey("practice_attempts.id", ondelete="CASCADE"))
    question_id: Mapped[UUID]
    answer_version: Mapped[int] = mapped_column(Integer)
    answer: Mapped[dict[str, Any]] = mapped_column(JSONB)
    question: Mapped[dict[str, Any]] = mapped_column(JSONB)
    request_key: Mapped[UUID]
    input_digest: Mapped[str] = mapped_column(String(64))


class PracticeGrade(UuidPrimaryKeyMixin, CreatedAtMixin, OwnerMixin, Base):
    __tablename__ = "practice_grades"
    __table_args__ = (
        UniqueConstraint("submission_id", "version", name="uq_practice_grade_version"),
    )
    submission_id: Mapped[UUID] = mapped_column(
        ForeignKey("practice_submissions.id", ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    rubric: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    run_id: Mapped[UUID | None]
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class PracticeRun(UuidPrimaryKeyMixin, TimestampMixin, OwnerMixin, SetReferenceMixin, Base):
    __tablename__ = "practice_runs"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "request_key", name="uq_practice_run_key"),
        Index("ix_practice_runs_due", "status", "created_at"),
        CheckConstraint(
            "status IN ('pending','processing','cancel_requested',"
            "'succeeded','failed','cancelled')",
            name="ck_practice_run_status",
        ),
    )
    operation: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    stage: Mapped[str] = mapped_column(String(32), default="waiting")
    request_key: Mapped[UUID]
    input_digest: Mapped[str] = mapped_column(String(64))
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    submission_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("practice_submissions.id", ondelete="CASCADE")
    )
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


class PracticeFeedback(UuidPrimaryKeyMixin, TimestampMixin, OwnerMixin, Base):
    __tablename__ = "practice_feedback"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "target_key", name="uq_practice_feedback_target"),
    )
    target_key: Mapped[str] = mapped_column(String(128))
    revision_id: Mapped[UUID | None]
    question_id: Mapped[UUID | None]
    grade_id: Mapped[UUID | None]
    feedback: Mapped[str | None] = mapped_column(String(16))
