from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from xuemian_ai.file_management.validation import normalize_digest, normalize_filename


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("知识库名称不能为空")
        return normalized


class KnowledgeBaseUpdate(KnowledgeBaseCreate):
    pass


class KnowledgeBaseView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    is_default: bool
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseStatistics(BaseModel):
    knowledge_base_count: int
    available_file_count: int
    processing_file_count: int
    latest_updated_name: str | None = None
    file_counts: dict[UUID, int] = Field(default_factory=dict)


class UploadSessionCreate(BaseModel):
    filename: str
    size: int = Field(gt=0)
    declared_mime: str | None = Field(default=None, max_length=128)
    client_sha256: str | None = None
    client_md5: str | None = None

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        return normalize_filename(value)

    @field_validator("client_sha256")
    @classmethod
    def validate_sha256(cls, value: str | None) -> str | None:
        return normalize_digest(value, "sha256")

    @field_validator("client_md5")
    @classmethod
    def validate_md5(cls, value: str | None) -> str | None:
        return normalize_digest(value, "md5")


class UploadPart(BaseModel):
    part_number: int = Field(ge=1, le=10_000)
    etag: str = Field(min_length=1, max_length=256)


class CompleteUploadRequest(BaseModel):
    parts: list[UploadPart] = Field(default_factory=list)


class SignPartsRequest(BaseModel):
    part_numbers: list[int] = Field(min_length=1, max_length=100)

    @field_validator("part_numbers")
    @classmethod
    def validate_unique_parts(cls, value: list[int]) -> list[int]:
        if any(number < 1 or number > 10_000 for number in value) or len(set(value)) != len(value):
            raise ValueError("分片编号不合法或重复")
        return value


class SignedPart(BaseModel):
    part_number: int
    upload_url: str


class UploadPlan(BaseModel):
    session_id: UUID
    status: str
    upload_mode: Literal["single", "multipart", "reuse"]
    expires_at: datetime
    upload_url: str | None = None
    part_size: int | None = None
    parts: list[SignedPart] = Field(default_factory=list)
    duplicate_file_asset_id: UUID | None = None


class UploadSessionView(BaseModel):
    session_id: UUID
    status: str
    upload_mode: str
    filename: str
    size: int
    expires_at: datetime
    failure_code: str | None = None
    knowledge_file_id: UUID | None = None
    duplicate_file_asset_id: UUID | None = None


class DuplicateResolutionRequest(BaseModel):
    action: Literal["LINK", "MOVE", "CANCEL"]


class KnowledgeFileUpdate(BaseModel):
    display_name: str

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        return normalize_filename(value)


class KnowledgeFileMove(BaseModel):
    target_knowledge_base_id: UUID


class KnowledgeFileView(BaseModel):
    id: UUID
    display_name: str
    detected_mime: str
    byte_size: int
    processing_status: str
    validation_status: str
    created_at: datetime
    updated_at: datetime


class DownloadUrlView(BaseModel):
    url: str
    expires_in: int


class DeletionImpactView(BaseModel):
    target_id: UUID
    conversations: int = 0
    questions: int = 0
    reports: int = 0
    notes: int = 0
    weaknesses: int = 0
    confirmation_token: str
    expires_at: datetime


class DeleteRequest(BaseModel):
    confirmation_token: str
    mode: Literal["SOURCE_ONLY", "CASCADE"] = "SOURCE_ONLY"


class DeleteResult(BaseModel):
    target_id: UUID
    status: Literal["deleted"] = "deleted"


class FilePolicyView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version: int
    status: str
    rules: dict[str, object]
    base_version_id: UUID | None
    published_by: UUID | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class FilePolicyDraftRequest(BaseModel):
    rules: dict[str, object]
    base_version_id: UUID | None = None


class FilePolicyUpdateRequest(BaseModel):
    rules: dict[str, object]


class FilePolicyPublishRequest(BaseModel):
    base_version_id: UUID | None = None
