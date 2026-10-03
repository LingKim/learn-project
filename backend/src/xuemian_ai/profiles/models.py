from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from xuemian_ai.infrastructure.database import Base
from xuemian_ai.persistence.mixins import ActorAuditMixin, TimestampMixin, UuidPrimaryKeyMixin


class UserProfile(UuidPrimaryKeyMixin, TimestampMixin, ActorAuditMixin, Base):
    __tablename__ = "user_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_profiles_user_id"),
        CheckConstraint(
            "experience_months IS NULL OR experience_months BETWEEN 0 AND 720",
            name="ck_user_profiles_experience_months",
        ),
        CheckConstraint(
            "target_level IS NULL OR target_level IN "
            "('intern', 'junior', 'intermediate', 'senior', 'expert')",
            name="ck_user_profiles_target_level",
        ),
        CheckConstraint(
            "preferred_language IS NULL OR preferred_language IN ('zh-CN', 'en-US')",
            name="ck_user_profiles_preferred_language",
        ),
        CheckConstraint("version >= 1", name="ck_user_profiles_version"),
        CheckConstraint(
            "navigation_position IN ('left', 'top')", name="ck_user_profiles_navigation_position"
        ),
        Index("ix_user_profiles_avatar", "avatar_file_asset_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    target_job: Mapped[str | None] = mapped_column(String(120), nullable=True)
    experience_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    target_skills: Mapped[list[str] | None] = mapped_column(ARRAY(String(50)), nullable=True)
    focus_topics: Mapped[list[str] | None] = mapped_column(ARRAY(String(80)), nullable=True)
    learning_goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    navigation_position: Mapped[str] = mapped_column(
        String(8), nullable=False, default="left", server_default="left"
    )
    avatar_file_asset_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("file_assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
