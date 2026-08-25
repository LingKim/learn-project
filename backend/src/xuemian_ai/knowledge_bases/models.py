from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from xuemian_ai.infrastructure.database import Base
from xuemian_ai.persistence.mixins import (
    ActorAuditMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UuidPrimaryKeyMixin,
)


class KnowledgeBase(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    ActorAuditMixin,
    SoftDeleteMixin,
    Base,
):
    __tablename__ = "knowledge_bases"
    __table_args__ = (
        Index("ix_knowledge_bases_owner_user_id", "owner_user_id"),
        Index(
            "uq_knowledge_bases_active_default_owner",
            "owner_user_id",
            unique=True,
            postgresql_where=text("is_default = true AND deleted_at IS NULL"),
        ),
    )

    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
