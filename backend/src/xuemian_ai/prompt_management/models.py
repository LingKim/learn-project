from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
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
from sqlalchemy.orm import Mapped, mapped_column

from xuemian_ai.infrastructure.database import Base
from xuemian_ai.persistence.mixins import (
    CreatedAtMixin,
    CreatedByMixin,
    TimestampMixin,
    UuidPrimaryKeyMixin,
)


class PromptDefinition(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prompt_definitions"
    __table_args__ = (
        UniqueConstraint("definition_key", name="uq_prompt_definition_key"),
        UniqueConstraint(
            "agent_key", "scene_key", "template_kind", name="uq_prompt_definition_scene"
        ),
        CheckConstraint(
            "template_kind IN ('shared','agent','task')", name="ck_prompt_definition_kind"
        ),
        CheckConstraint(
            "runtime_status IN ('enabled','disabled')", name="ck_prompt_definition_status"
        ),
    )
    definition_key: Mapped[str] = mapped_column(String(100))
    agent_key: Mapped[str] = mapped_column(String(64))
    scene_key: Mapped[str] = mapped_column(String(64))
    template_kind: Mapped[str] = mapped_column(String(16))
    display_name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(1000))
    runtime_status: Mapped[str] = mapped_column(String(16), default="enabled")
    active_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "prompt_versions.id",
            use_alter=True,
            name="fk_prompt_definition_active",
            ondelete="RESTRICT",
        )
    )


class PromptVersion(UuidPrimaryKeyMixin, CreatedAtMixin, CreatedByMixin, Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("definition_id", "version", name="uq_prompt_version_number"),
        Index(
            "uq_prompt_version_published",
            "definition_id",
            unique=True,
            postgresql_where=text("status = 'published'"),
        ),
        CheckConstraint("version >= 1 AND revision >= 1", name="ck_prompt_version_positive"),
        CheckConstraint(
            "status IN ('draft','published','retired')", name="ck_prompt_version_status"
        ),
    )
    definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("prompt_definitions.id", ondelete="RESTRICT")
    )
    version: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    content: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))
    variables: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    change_description: Mapped[str] = mapped_column(String(1000))
    base_active_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="RESTRICT")
    )
    rollback_from_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="RESTRICT")
    )
    published_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PromptVersionDependency(UuidPrimaryKeyMixin, Base):
    __tablename__ = "prompt_version_dependencies"
    __table_args__ = (
        UniqueConstraint("root_version_id", "slot", "position", name="uq_prompt_dependency_slot"),
        UniqueConstraint(
            "root_version_id", "dependency_version_id", name="uq_prompt_dependency_version"
        ),
        CheckConstraint(
            "root_version_id <> dependency_version_id AND position >= 0",
            name="ck_prompt_dependency_identity",
        ),
        CheckConstraint("slot IN ('global','agent')", name="ck_prompt_dependency_slot"),
    )
    root_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="RESTRICT")
    )
    dependency_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="RESTRICT")
    )
    slot: Mapped[str] = mapped_column(String(16))
    position: Mapped[int] = mapped_column(Integer)
    dependency_sha256: Mapped[str] = mapped_column(String(64))


class PromptEvaluationSuite(UuidPrimaryKeyMixin, CreatedAtMixin, CreatedByMixin, Base):
    __tablename__ = "prompt_evaluation_suites"
    __table_args__ = (
        UniqueConstraint("agent_key", "scene_key", "version", name="uq_prompt_suite_version"),
    )
    agent_key: Mapped[str] = mapped_column(String(64))
    scene_key: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    cases: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    sha256: Mapped[str] = mapped_column(String(64))
    model_policy: Mapped[dict[str, Any]] = mapped_column(JSONB)


class PromptEvaluationRun(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "prompt_evaluation_runs"
    prompt_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="RESTRICT")
    )
    evaluation_suite_id: Mapped[UUID] = mapped_column(
        ForeignKey("prompt_evaluation_suites.id", ondelete="RESTRICT")
    )
    evaluation_fingerprint: Mapped[str] = mapped_column(String(64))
    model_configuration: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16))
    case_results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    passed: Mapped[bool] = mapped_column(default=False)
    error_key: Mapped[str | None] = mapped_column(String(64))
    executed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PromptAuditEvent(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    """审计只接受结构化身份，不能给任意 payload 留下泄露正文的旁路。"""

    __tablename__ = "prompt_audit_events"
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(32))
    outcome: Mapped[str] = mapped_column(String(16))
    target_id: Mapped[UUID | None]
    version: Mapped[int | None]
    request_id: Mapped[str] = mapped_column(String(128))
