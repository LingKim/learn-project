from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
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


class LearningConversation(
    UuidPrimaryKeyMixin, TimestampMixin, ActorAuditMixin, SoftDeleteMixin, Base
):
    __tablename__ = "learning_conversations"
    __table_args__ = (
        CheckConstraint("mode IN ('materials','general')", name="ck_learning_mode"),
        CheckConstraint(
            "(mode = 'materials' AND knowledge_base_id IS NOT NULL) OR "
            "(mode = 'general' AND knowledge_base_id IS NULL)",
            name="ck_learning_scope",
        ),
        Index("ix_learning_conversation_owner", "user_id", "deleted_at", "updated_at"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    mode: Mapped[str] = mapped_column(String(16))
    # 软删除来源后仍保留会话；所有后续访问由业务授权复核。
    knowledge_base_id: Mapped[UUID | None]
    file_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    title: Mapped[str] = mapped_column(String(80), default="新问答")


class LearningTurn(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "learning_turns"
    __table_args__ = (
        Index("uq_learning_turn_request", "conversation_id", "request_key", unique=True),
        Index(
            "uq_learning_turn_processing",
            "conversation_id",
            unique=True,
            postgresql_where=text("status = 'processing'"),
        ),
        CheckConstraint(
            "status IN ('processing','succeeded','failed')", name="ck_learning_turn_status"
        ),
        CheckConstraint(
            "feedback IS NULL OR feedback IN ('helpful','unhelpful')", name="ck_learning_feedback"
        ),
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("learning_conversations.id", ondelete="CASCADE")
    )
    request_key: Mapped[UUID]
    question: Mapped[str] = mapped_column(Text)
    question_digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    lease_token: Mapped[UUID]
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=1)
    answer: Mapped[str | None] = mapped_column(Text)
    refused: Mapped[bool] = mapped_column(Boolean, default=False)
    # 只记录来源 ID，不保留来源正文快照；读取时复核当前授权。
    citations: Mapped[list[dict[str, str | int]]] = mapped_column(JSONB, default=list)
    trace_id: Mapped[UUID | None]
    trace_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    feedback: Mapped[str | None] = mapped_column(String(16))
    agent_key: Mapped[str] = mapped_column(String(64))
    scene_key: Mapped[str] = mapped_column(String(64))
    prompt_manifest: Mapped[dict[str, object]] = mapped_column(JSONB)
    model_parameters: Mapped[dict[str, object]] = mapped_column(JSONB)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer)
