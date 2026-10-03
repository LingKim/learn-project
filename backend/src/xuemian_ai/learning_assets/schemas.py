from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from xuemian_ai.practice.schemas import SourceRef, StrictModel

Decision = Literal["pending", "confirmed", "ignored", "revoked"]
MasteryState = Literal["to_learn", "learning", "to_verify", "mastered"]
Severity = Literal["low", "medium", "high"]
Foundation = Literal["unfamiliar", "know_concept", "used_unfamiliar", "review"]
Depth = Literal["quick", "systematic", "deep"]


class SourceConfig(StrictModel):
    source_mode: Literal["general", "materials"] = "general"
    knowledge_base_id: UUID | None = None
    file_ids: list[UUID] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def scope(self) -> Self:
        if self.source_mode == "materials" and self.knowledge_base_id is None:
            raise ValueError("资料模式需要知识库")
        if self.source_mode == "general" and (self.knowledge_base_id or self.file_ids):
            raise ValueError("通用模式不能包含资料范围")
        if len(self.file_ids) != len(set(self.file_ids)):
            raise ValueError("文件不能重复")
        return self


class WeaknessCreate(SourceConfig):
    title: str = Field(min_length=1, max_length=120)
    domain: str | None = Field(default=None, max_length=120)
    tags: list[str] = Field(default_factory=list, max_length=20)
    severity: Severity = "medium"
    request_key: UUID

    @model_validator(mode="after")
    def nonblank(self) -> Self:
        if not self.title.strip() or any(not tag.strip() or len(tag) > 60 for tag in self.tags):
            raise ValueError("名称和标签不能为空，标签最多60字")
        return self


class VersionRequest(StrictModel):
    expected_version: int = Field(ge=1)


class ConfirmRequest(VersionRequest):
    request_key: UUID


class WeaknessPatch(VersionRequest):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    domain: str | None = Field(default=None, max_length=120)
    tags: list[str] | None = Field(default=None, max_length=20)
    severity: Severity | None = None

    @model_validator(mode="after")
    def nonblank(self) -> Self:
        if self.title is not None and not self.title.strip():
            raise ValueError("名称不能为空")
        if self.tags is not None and any(not tag.strip() or len(tag) > 60 for tag in self.tags):
            raise ValueError("标签不能为空，最多60字")
        return self


class MasteryRequest(VersionRequest):
    mastery_state: MasteryState


class ExplanationConfig(SourceConfig):
    topic: str = Field(default="", max_length=500)
    foundation: Foundation = "know_concept"
    depth: Depth = "systematic"
    preferred_language: Literal["zh-CN", "en-US"] | None = None
    target_job: str | None = Field(default=None, max_length=120)
    experience_months: int | None = Field(default=None, ge=0, le=720)
    target_level: Literal["intern", "junior", "intermediate", "senior", "expert"] | None = None
    target_skills: list[str] | None = Field(default=None, max_length=30)
    focus_topics: list[str] | None = Field(default=None, max_length=30)
    learning_goal: str | None = Field(default=None, max_length=2000)


class ExplanationCreate(ExplanationConfig):
    weakness_id: UUID | None = None
    weakness_version: int | None = Field(default=None, ge=1)
    request_key: UUID

    @model_validator(mode="after")
    def target(self) -> Self:
        if bool(self.weakness_id) != bool(self.weakness_version):
            raise ValueError("难点需要同时提供版本")
        if not self.weakness_id and not self.topic.strip():
            raise ValueError("请输入知识点或选择难点")
        return self


class ExplanationRegenerate(VersionRequest):
    request_key: UUID
    config: ExplanationConfig | None = None


class KnowledgeExample(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=6000)


class UnderstandingExercise(StrictModel):
    question: str = Field(min_length=1, max_length=3000)
    self_check_points: list[str] = Field(min_length=1, max_length=20)


class KnowledgeCardPayload(StrictModel):
    concept: str = Field(min_length=1, max_length=6000)
    applications: list[str] = Field(min_length=1, max_length=20)
    principles: list[str] = Field(min_length=1, max_length=20)
    examples: list[KnowledgeExample] = Field(min_length=1, max_length=10)
    misconceptions: list[str] = Field(min_length=1, max_length=20)
    exercises: list[UnderstandingExercise] = Field(min_length=1, max_length=10)
    citations: list[SourceRef] = Field(default_factory=list, max_length=30)
    source_mode: Literal["general", "materials"]

    @model_validator(mode="after")
    def content_budget(self) -> Self:
        texts = [self.concept, *self.applications, *self.principles, *self.misconceptions]
        texts += [item.content for item in self.examples]
        texts += [item.question for item in self.exercises]
        texts += [text for item in self.exercises for text in item.self_check_points]
        if any(not text.strip() or len(text) > 6000 for text in texts):
            raise ValueError("精讲部分不可为空或超过6000字")
        if sum(map(len, texts)) > 40000:
            raise ValueError("精讲正文超出40000字预算")
        if self.source_mode == "materials" and not self.citations:
            raise ValueError("资料精讲需要合法引用")
        if self.source_mode == "general" and self.citations:
            raise ValueError("通用知识不能伪造资料引用")
        if len({ref.source_id for ref in self.citations}) != len(self.citations):
            raise ValueError("引用不能重复")
        return self


class KnowledgeResultRef(StrictModel):
    type: Literal["card"] = "card"
    id: UUID
    explanation_id: UUID
    version: int = Field(ge=1)


class KnowledgeRunView(StrictModel):
    id: UUID
    explanation_id: UUID
    operation: Literal["generate", "regenerate"]
    status: Literal["pending", "processing", "cancel_requested", "succeeded", "failed", "cancelled"]
    stage: str
    attempt_count: int
    retryable: bool
    error_key: str | None
    result_ref: KnowledgeResultRef | None
    request_key: UUID
    input_digest: str


class KnowledgeCardView(KnowledgeCardPayload):
    config: ExplanationConfig
    id: UUID
    explanation_id: UUID
    version: int
    parent_version: int | None
    foundation: Foundation
    depth: Depth
    preferred_language: Literal["zh-CN", "en-US"]
    source_available: bool
    created_at: datetime


class ExplanationView(StrictModel):
    id: UUID
    weakness_id: UUID | None
    topic: str
    version: int
    config: ExplanationConfig
    active_card_version: int | None
    source_available: bool
    created_at: datetime
    updated_at: datetime


class LearningReviewView(StrictModel):
    id: UUID
    target_kind: Literal["weakness", "explanation"]
    target_id: UUID
    target_snapshot: dict[str, object]
    set_id: UUID
    attempt_id: UUID
    version: int
    source_available: bool
    total_related: int
    submitted_count: int
    graded_count: int
    correct_count: int
    low_confidence_count: int
    validation_passed: bool
    conclusion: str
    created_at: datetime


class ExplanationDetail(ExplanationView):
    reviews: list[LearningReviewView] = Field(default_factory=list)
    card_versions: list[int] = Field(default_factory=list)
    card: KnowledgeCardView | None
    run: KnowledgeRunView | None


class ExplanationAccepted(StrictModel):
    explanation: ExplanationView
    run: KnowledgeRunView


class WeaknessView(SourceConfig):
    id: UUID
    title: str
    domain: str | None
    tags: list[str]
    severity: Severity
    decision: Decision
    mastery_state: MasteryState
    version: int
    evidence_sufficient: bool
    evidence_count: int = 0
    available_evidence_count: int = 0
    source_available: bool
    policy_version: str
    explanation_id: UUID | None
    active_card_version: int | None
    run: KnowledgeRunView | None
    created_at: datetime
    updated_at: datetime


class EvidenceView(StrictModel):
    id: UUID
    kind: Literal["practice", "manual"]
    question_id: UUID | None
    attempt_id: UUID | None
    submission_id: UUID | None
    grade_id: UUID | None
    grade_version: int | None
    submitted_at: datetime | None
    available: bool
    superseded: bool
    ignored: bool
    detail: dict[str, object] | None
    created_at: datetime


class WeaknessEventView(StrictModel):
    id: UUID
    event_type: str
    version: int
    payload: dict[str, object]
    created_at: datetime


class WeaknessDetail(WeaknessView):
    card_versions: list[int] = Field(default_factory=list)
    evidence: list[EvidenceView]
    events: list[WeaknessEventView]
    card: KnowledgeCardView | None
    reviews: list[LearningReviewView]
