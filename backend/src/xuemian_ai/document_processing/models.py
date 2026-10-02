from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from xuemian_ai.infrastructure.database import Base
from xuemian_ai.persistence.mixins import TimestampMixin, UuidPrimaryKeyMixin


class AIProcessingConsent(UuidPrimaryKeyMixin, Base):
    __tablename__ = "ai_processing_consents"
    __table_args__ = (
        UniqueConstraint("user_id", "terms_version", name="uq_ai_processing_consent"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    terms_version: Mapped[str] = mapped_column(String(32))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BackgroundTask(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "background_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','processing','cancel_requested',"
            "'succeeded','failed','cancelled')",
            name="ck_background_task_status",
        ),
        Index("ix_background_tasks_due", "status", "next_attempt_at"),
        Index(
            "uq_background_tasks_active",
            "file_asset_id",
            unique=True,
            postgresql_where=text("status IN ('pending','processing','cancel_requested')"),
        ),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    file_asset_id: Mapped[UUID] = mapped_column(ForeignKey("file_assets.id", ondelete="CASCADE"))
    task_type: Mapped[str] = mapped_column(String(32), default="document_processing")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    stage: Mapped[str] = mapped_column(String(32), default="waiting")
    completed_units: Mapped[int | None] = mapped_column(Integer)
    total_units: Mapped[int | None] = mapped_column(Integer)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_token: Mapped[UUID | None]
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_generation: Mapped[int] = mapped_column(Integer)
    result_reference: Mapped[UUID | None]
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    retryable: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProcessingAttempt(UuidPrimaryKeyMixin, Base):
    __tablename__ = "document_processing_attempts"
    __table_args__ = (UniqueConstraint("task_id", "attempt_number", name="uq_processing_attempt"),)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("background_tasks.id", ondelete="CASCADE"))
    attempt_number: Mapped[int] = mapped_column(Integer)
    lease_token: Mapped[UUID]
    status: Mapped[str] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VectorIndexProfile(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vector_index_profiles"
    __table_args__ = (UniqueConstraint("profile_key", name="uq_vector_profile_key"),)
    profile_key: Mapped[str] = mapped_column(String(128))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    dimensions: Mapped[int] = mapped_column(Integer)
    distance: Mapped[str] = mapped_column(String(32))
    collection: Mapped[str] = mapped_column(String(128))
    schema_version: Mapped[str] = mapped_column(String(32))
    vector_name: Mapped[str] = mapped_column(String(32), default="dense")


class DocumentProcessingVersion(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_processing_versions"
    __table_args__ = (
        UniqueConstraint("file_asset_id", "version_number", name="uq_processing_version_number"),
        CheckConstraint(
            "status IN ('draft','active','retired','failed','cancelled')",
            name="ck_processing_version_status",
        ),
        Index(
            "uq_processing_active_version",
            "file_asset_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    file_asset_id: Mapped[UUID] = mapped_column(ForeignKey("file_assets.id", ondelete="CASCADE"))
    task_id: Mapped[UUID] = mapped_column(ForeignKey("background_tasks.id", ondelete="CASCADE"))
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("vector_index_profiles.id", ondelete="RESTRICT")
    )
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    parser_version: Mapped[str] = mapped_column(String(128))
    chunk_strategy_version: Mapped[str] = mapped_column(String(64))
    ocr_strategy_version: Mapped[str] = mapped_column(String(64))
    character_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    image_count: Mapped[int] = mapped_column(Integer, default=0)
    unrecognized_image_count: Mapped[int] = mapped_column(Integer, default=0)
    native_page_count: Mapped[int] = mapped_column(Integer, default=0)
    ocr_page_count: Mapped[int] = mapped_column(Integer, default=0)
    ocr_low_quality_page_count: Mapped[int] = mapped_column(Integer, default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(64))


class DocumentChunk(UuidPrimaryKeyMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("processing_version_id", "ordinal", name="uq_document_chunk_ordinal"),
        Index("ix_document_chunk_search", "search_vector", postgresql_using="gin"),
    )
    processing_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_processing_versions.id", ondelete="CASCADE")
    )
    file_asset_id: Mapped[UUID] = mapped_column(ForeignKey("file_assets.id", ondelete="CASCADE"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    content_digest: Mapped[str] = mapped_column(String(64))
    source_kind: Mapped[str] = mapped_column(String(32))
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    paragraph_start: Mapped[int | None] = mapped_column(Integer)
    paragraph_end: Mapped[int | None] = mapped_column(Integer)
    heading_path: Mapped[list[str]] = mapped_column(JSONB, default=list)
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    search_vector: Mapped[str] = mapped_column(TSVECTOR)


class VectorOperation(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_vector_operations"
    __table_args__ = (UniqueConstraint("processing_version_id", name="uq_vector_cleanup_version"),)
    user_id: Mapped[UUID]
    file_asset_id: Mapped[UUID]
    processing_version_id: Mapped[UUID]
    collection: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(64))


class RetrievalTrace(UuidPrimaryKeyMixin, Base):
    __tablename__ = "retrieval_traces"
    __table_args__ = (Index("ix_retrieval_trace_expiry", "expires_at"),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    knowledge_base_id: Mapped[UUID]
    request_id: Mapped[str | None] = mapped_column(String(128))
    query_digest: Mapped[str] = mapped_column(String(64))
    query_length: Mapped[int] = mapped_column(Integer)
    strategy_version: Mapped[str] = mapped_column(String(128))
    stages: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    final_chunk_ids: Mapped[list[str]] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    retained_by_case: Mapped[bool] = mapped_column(Boolean, default=False)
