from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from xuemian_ai.document_processing.schemas import EvidenceChunk


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["materials", "general"]
    knowledge_base_id: UUID | None = None
    file_ids: list[UUID] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def scope_matches_mode(self) -> "ConversationCreate":
        if self.mode == "materials" and self.knowledge_base_id is None:
            raise ValueError("资料模式必须选择知识库")
        if self.mode == "general" and (self.knowledge_base_id is not None or self.file_ids):
            raise ValueError("通用模式不能指定资料范围")
        if len(self.file_ids) != len(set(self.file_ids)):
            raise ValueError("文件范围不得重复")
        return self


class ConversationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    mode: Literal["materials", "general"]
    knowledge_base_id: UUID | None
    file_ids: list[UUID]
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=80)

    @field_validator("title")
    @classmethod
    def trim_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("标题不能为空")
        return value.strip()


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: UUID
    language: Literal["zh", "en"] | None = None
    question: str = Field(min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def trim_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("问题不能为空")
        return value.strip()


class GeneratedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    answer: str = Field(min_length=1, max_length=12000)
    refused: bool
    citation_ids: list[int] = Field(max_length=8)


class AnswerCitation(BaseModel):
    number: int
    available: bool
    evidence: EvidenceChunk | None


class TurnView(BaseModel):
    id: UUID
    request_key: UUID
    language: Literal["zh", "en"]
    question: str
    status: Literal["processing", "succeeded", "failed"]
    answer: str | None
    refused: bool
    source_label: Literal["用户资料", "模型通用知识"]
    citations: list[AnswerCitation]
    trace_id: UUID | None
    trace_complete: bool
    error_code: str | None
    feedback: Literal["helpful", "unhelpful"] | None
    created_at: datetime


class ConversationDetail(BaseModel):
    conversation: ConversationView
    turns: list[TurnView]


class FeedbackRequest(BaseModel):
    feedback: Literal["helpful", "unhelpful"] | None


class AnswerStreamEvent(BaseModel):
    type: Literal["started", "delta", "completed", "failed"]
    turn: TurnView | None = None
    delta: str | None = None
    error_code: str | None = None
    message: str | None = None
