from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
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
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from xuemian_ai.infrastructure.database import Base
from xuemian_ai.persistence.mixins import (
    ActorAuditMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UuidPrimaryKeyMixin,
)

UPLOAD_STATUSES = (
    "created",
    "uploading",
    "uploaded",
    "verifying",
    "duplicate_action_required",
    "completed",
    "failed",
    "cancelled",
    "expired",
)
OBJECT_STATUSES = ("staged", "validating", "available", "deleting", "deleted", "missing")
VALIDATION_STATUSES = ("staged", "validating", "available", "rejected")
PROCESSING_STATUSES = (
    "pending_processing",
    "processing",
    "succeeded",
    "failed",
    "cancelled",
)
POLICY_STATUSES = ("draft", "published", "retired")
TASK_STATUSES = ("pending", "processing", "succeeded", "failed", "cancelled")


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class FilePolicyVersion(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "file_policy_versions"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_quoted(POLICY_STATUSES)})", name="ck_file_policy_versions_status"
        ),
        Index(
            "uq_file_policy_versions_published",
            "status",
            unique=True,
            postgresql_where=text("status = 'published'"),
        ),
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    rules: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    base_version_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("file_policy_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    published_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UploadSession(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "file_upload_sessions"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_quoted(UPLOAD_STATUSES)})", name="ck_file_upload_sessions_status"
        ),
        CheckConstraint("upload_mode IN ('single', 'multipart', 'reuse')", name="ck_upload_mode"),
        CheckConstraint(
            "purpose IN ('knowledge_document', 'avatar')", name="ck_file_upload_purpose"
        ),
        UniqueConstraint("owner_user_id", "idempotency_key", name="uq_upload_owner_idempotency"),
        Index("ix_file_upload_sessions_owner_status", "owner_user_id", "status"),
        Index("ix_file_upload_sessions_expires_at", "expires_at"),
    )

    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    knowledge_base_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=True,
    )
    purpose: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="knowledge_document",
        server_default="knowledge_document",
    )
    policy_version_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("file_policy_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    policy_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    declared_mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    declared_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    client_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_md5: Mapped[str | None] = mapped_column(String(32), nullable=True)
    upload_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    storage_domain: Mapped[str] = mapped_column(String(32), nullable=False)
    temporary_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    multipart_upload_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    result_knowledge_file_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    result_file_asset_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "file_assets.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_file_upload_sessions_result_file_asset_id",
        ),
        nullable=True,
    )
    requested_profile_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duplicate_file_asset_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StoredObject(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "stored_objects"
    __table_args__ = (
        CheckConstraint(f"status IN ({_quoted(OBJECT_STATUSES)})", name="ck_stored_objects_status"),
        UniqueConstraint("storage_domain", "sha256", "byte_size", name="uq_stored_object_identity"),
        Index("ix_stored_objects_status", "status"),
    )

    storage_domain: Mapped[str] = mapped_column(String(32), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    detected_mime: Mapped[str] = mapped_column(String(128), nullable=False)
    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    reference_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FileAsset(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    ActorAuditMixin,
    SoftDeleteMixin,
    Base,
):
    __tablename__ = "file_assets"
    __table_args__ = (
        CheckConstraint(
            f"validation_status IN ({_quoted(VALIDATION_STATUSES)})",
            name="ck_file_assets_validation_status",
        ),
        Index("ix_file_assets_owner", "owner_user_id"),
        Index("ix_file_assets_stored_object", "stored_object_id"),
    )

    owner_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    stored_object_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("stored_objects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    detected_mime: Mapped[str] = mapped_column(String(128), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(16), nullable=False)
    processing_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    validation_failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_version_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("file_policy_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_from_upload_session_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("file_upload_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )


class KnowledgeBaseFile(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    ActorAuditMixin,
    SoftDeleteMixin,
    Base,
):
    __tablename__ = "knowledge_base_files"
    __table_args__ = (
        CheckConstraint(
            f"processing_status IN ({_quoted(PROCESSING_STATUSES)})",
            name="ck_knowledge_base_files_processing_status",
        ),
        Index("ix_knowledge_base_files_knowledge_base", "knowledge_base_id"),
        Index("ix_knowledge_base_files_asset", "file_asset_id"),
        Index(
            "uq_knowledge_base_files_active_asset",
            "knowledge_base_id",
            "file_asset_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    knowledge_base_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_asset_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("file_assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False)
    processing_failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class FileAuditEvent(UuidPrimaryKeyMixin, Base):
    __tablename__ = "file_audit_events"
    __table_args__ = (
        Index("ix_file_audit_events_user", "actor_user_id"),
        Index("ix_file_audit_events_occurred", "occurred_at"),
    )

    actor_user_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FileCleanupTask(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "file_cleanup_tasks"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_quoted(TASK_STATUSES)})", name="ck_file_cleanup_tasks_status"
        ),
        UniqueConstraint("idempotency_key", name="uq_file_cleanup_tasks_idempotency"),
        Index("ix_file_cleanup_tasks_due", "status", "next_attempt_at", "priority"),
    )

    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)


class FileOrphanCandidate(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "file_orphan_candidates"
    __table_args__ = (UniqueConstraint("bucket", "object_key", name="uq_file_orphan_object"),)

    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    delete_enqueued: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class FileDeletionTombstone(UuidPrimaryKeyMixin, Base):
    __tablename__ = "file_deletion_tombstones"
    __table_args__ = (
        UniqueConstraint("stored_object_id", name="uq_file_deletion_tombstone_object"),
        Index("ix_file_deletion_tombstones_deleted_at", "deleted_at"),
    )

    stored_object_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    storage_domain: Mapped[str] = mapped_column(String(32), nullable=False)
    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
