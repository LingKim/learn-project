from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AIConsentRequest(BaseModel):
    confirmed: Literal[True]
    terms_version: str = Field(min_length=1, max_length=32)


class AIConsentView(BaseModel):
    confirmed: bool
    terms_version: str
    notice: str


class ProcessingVersionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    version_number: int
    chunk_count: int
    image_count: int
    unrecognized_image_count: int
    native_page_count: int
    ocr_page_count: int


class ProcessingTaskView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    status: str
    stage: str
    completed_units: int | None
    total_units: int | None
    attempt_count: int
    last_error_code: str | None
    retryable: bool
    created_at: datetime
    requires_ai_consent: bool = False
    active_version: ProcessingVersionView | None = None


class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    file_ids: list[UUID] = Field(default_factory=list, max_length=100)
    top_n: int = Field(default=8, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def trim_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("检索问题不能为空")
        return value.strip()

    @field_validator("file_ids")
    @classmethod
    def unique_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("文件范围不得重复")
        return value


class EvidenceChunk(BaseModel):
    chunk_id: UUID
    file_id: UUID
    file_name: str
    processing_version_id: UUID
    content: str
    score: float
    source_kind: str
    page_start: int | None
    page_end: int | None
    paragraph_start: int | None
    paragraph_end: int | None
    heading_path: list[str]
    ocr_confidence: float | None


class RetrievalResult(BaseModel):
    trace_id: UUID
    trace_complete: bool
    evidence: list[EvidenceChunk]
