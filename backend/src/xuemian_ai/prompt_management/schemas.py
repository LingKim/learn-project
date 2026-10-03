from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class Variable(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    type: Literal["string", "object"]
    required: bool = True
    max_length: int = Field(default=100000, ge=1, le=200000)
    sources: list[Literal["default"]] = Field(default=["default"])
    sensitive: bool = False


class DependencyInput(StrictModel):
    version_id: UUID
    slot: Literal["global", "agent"]
    position: int = Field(default=0, ge=0)


class DependencyView(StrictModel):
    version_id: UUID
    slot: Literal["global", "agent", "task"]
    position: int = Field(default=0, ge=0)
    definition_key: str
    sha256: str


class DraftCreate(StrictModel):
    expected_active_version_id: UUID | None
    source_version_id: UUID | None = None
    content: str | None = Field(default=None, max_length=20000)
    change_description: str = Field(min_length=1, max_length=1000)
    dependencies: list[DependencyInput] | None = None


class DraftPatch(StrictModel):
    expected_revision: int = Field(ge=1)
    content: str = Field(min_length=1, max_length=20000)
    variables: list[Variable]
    dependencies: list[DependencyInput]
    change_description: str = Field(min_length=1, max_length=1000)


class PublishRequest(StrictModel):
    expected_active_version_id: UUID | None
    expected_revision: int = Field(ge=1)


class RollbackRequest(StrictModel):
    expected_active_version_id: UUID | None
    target_version_id: UUID
    reason: str = Field(min_length=1, max_length=1000)


class StatusRequest(StrictModel):
    expected_active_version_id: UUID | None
    runtime_status: Literal["enabled", "disabled"]


class DefinitionView(StrictModel):
    id: UUID
    definition_key: str
    agent_key: str
    scene_key: str
    template_kind: Literal["shared", "agent", "task"]
    display_name: str
    description: str
    runtime_status: Literal["enabled", "disabled"]
    active_version_id: UUID | None
    created_at: datetime
    updated_at: datetime
    contract_sha256: str | None = None


class VersionSummary(StrictModel):
    id: UUID
    definition_id: UUID
    version: int
    revision: int
    status: Literal["draft", "published", "retired"]
    content_sha256: str
    change_description: str
    base_active_version_id: UUID | None
    rollback_from_version_id: UUID | None
    created_at: datetime
    published_at: datetime | None
    latest_evaluation: "EvaluationView | None" = None


class VersionView(VersionSummary):
    content: str
    variables: list[Variable]
    dependencies: list[DependencyView]


class EvaluationView(StrictModel):
    id: UUID
    prompt_version_id: UUID
    evaluation_suite_id: UUID
    evaluation_fingerprint: str
    model_configuration: dict[str, Any]
    status: Literal["processing", "succeeded", "failed"]
    case_results: list[dict[str, Any]]
    metrics: dict[str, Any]
    passed: bool
    error_key: str | None
    started_at: datetime
    ended_at: datetime | None


class PreviewRequest(StrictModel):
    variables: dict[str, Any] = Field(default_factory=dict)


class PreviewView(StrictModel):
    system_messages: list[str]
    data_message: dict[str, Any]
    composition: list[DependencyView]
    contract_sha256: str
    output_schema_sha256: str
    message_lengths: list[int]


class DiffView(StrictModel):
    version_id: UUID
    base_version_id: UUID | None
    content_diff: str
    variables_changed: bool
    dependencies_changed: bool


class AuditView(StrictModel):
    id: UUID
    actor_user_id: UUID | None
    action: str
    outcome: str
    target_id: UUID | None
    version: int | None
    request_id: str
    created_at: datetime


class RegistryEntryView(StrictModel):
    definition_key: str
    agent_key: str
    scene_key: str
    template_kind: Literal["shared", "agent", "task"]
    display_name: str
    description: str
    variables: list[Variable]
    contract_sha256: str
    dependencies: list[dict[str, str]]
    tools: list[str]
