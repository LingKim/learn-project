from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class UuidPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UpdatedAtMixin:
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TimestampMixin(CreatedAtMixin, UpdatedAtMixin):
    pass


class CreatedByMixin:
    @declared_attr
    def created_by(cls) -> Mapped[UUID | None]:
        return mapped_column(
            PostgreSQLUUID(as_uuid=True),
            ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        )


class UpdatedByMixin:
    @declared_attr
    def updated_by(cls) -> Mapped[UUID | None]:
        return mapped_column(
            PostgreSQLUUID(as_uuid=True),
            ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        )


class ActorAuditMixin(CreatedByMixin, UpdatedByMixin):
    pass


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @declared_attr
    def deleted_by(cls) -> Mapped[UUID | None]:
        return mapped_column(
            PostgreSQLUUID(as_uuid=True),
            ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        )
