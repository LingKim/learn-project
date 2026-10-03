from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from xuemian_ai.infrastructure.database import Base
from xuemian_ai.persistence.mixins import TimestampMixin, UuidPrimaryKeyMixin


class AgentRun(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """与真实 PracticeRun 一对一绑定；历史业务内容仍由原领域保存。"""

    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint("practice_run_id", name="uq_agent_run_practice"),
        Index("ix_agent_run_owner", "owner_user_id", "created_at"),
        CheckConstraint(
            "status IN ('pending','processing','succeeded','failed','cancelled')",
            name="ck_agent_run_status",
        ),
    )
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    practice_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("practice_runs.id", ondelete="CASCADE")
    )
    agent_key: Mapped[str] = mapped_column(String(64))
    scene_key: Mapped[str] = mapped_column(String(64))
    root_prompt_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("prompt_versions.id", name="fk_agent_run_prompt_version", ondelete="RESTRICT")
    )
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    input_reference: Mapped[dict[str, Any]] = mapped_column(JSONB)
    output_reference: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    request_id: Mapped[str | None] = mapped_column(String(128))
    trace_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    error_key: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
