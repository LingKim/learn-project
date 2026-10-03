from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from xuemian_ai.infrastructure.database import Base
from xuemian_ai.persistence.mixins import (
    ActorAuditMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UuidPrimaryKeyMixin,
)


class LearningAttachment(
    UuidPrimaryKeyMixin, TimestampMixin, ActorAuditMixin, SoftDeleteMixin, Base
):
    __tablename__ = "learning_attachments"
    __table_args__ = (
        Index("ix_learning_attachments_owner", "owner_user_id"),
        Index("ix_learning_attachments_turn", "turn_id"),
        Index("ix_learning_attachments_expires", "expires_at"),
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    file_asset_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("file_assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    turn_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("learning_turns.id", ondelete="CASCADE"),
        nullable=True,
    )
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
