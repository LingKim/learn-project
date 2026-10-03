from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

QuestionType = Literal[
    "single_choice", "multiple_choice", "true_false", "short_answer", "code_text"
]
Difficulty = Literal["easy", "medium", "hard"]


def default_question_types() -> dict[QuestionType, int]:
    return {"single_choice": 5}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PracticeConfig(StrictModel):
    mode: Literal["practice"] = "practice"
    source_mode: Literal["materials", "general"] = "general"
    knowledge_base_id: UUID | None = None
    file_ids: list[UUID] = Field(default_factory=list)
    topic: str = Field(default="", max_length=500)
    target_job: str | None = Field(default=None, max_length=120)
    experience_months: int | None = Field(default=None, ge=0, le=720)
    target_level: Literal["intern", "junior", "intermediate", "senior", "expert"] | None = None
    target_skills: list[str] | None = None
    focus_topics: list[str] | None = None
    learning_goal: str | None = Field(default=None, max_length=2000)
    preferred_language: Literal["zh-CN", "en-US"] | None = None
    difficulty: Difficulty = "medium"
    question_count: int = Field(default=5, ge=1, le=20)
    question_types: dict[QuestionType, int] = Field(default_factory=default_question_types)

    @model_validator(mode="after")
    def valid(self) -> Self:
        if (
            any(n < 0 for n in self.question_types.values())
            or sum(self.question_types.values()) != self.question_count
        ):
            raise ValueError("题型数量之和必须等于题量")
        if self.source_mode == "materials" and not self.knowledge_base_id:
            raise ValueError("资料模式需要知识库")
        if self.source_mode == "general" and (self.knowledge_base_id or self.file_ids):
            raise ValueError("通用知识模式不能包含资料范围")
        if len(set(self.file_ids)) != len(self.file_ids):
            raise ValueError("文件不能重复")
        return self


class SourceRef(StrictModel):
    source_id: str
    file_id: UUID
    file_asset_id: UUID
    processing_version_id: UUID
    chunk_id: UUID
    display_name: str
    page_start: int | None = None
    page_end: int | None = None
    paragraph_start: int | None = None
    paragraph_end: int | None = None


class Option(StrictModel):
    id: str = Field(min_length=1, max_length=32)
    text: str = Field(min_length=1, max_length=2000)


class RubricDimension(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=2000)
    max_score: float | None = Field(default=None, gt=0, le=100)


class QuestionBase(StrictModel):
    question_id: UUID
    difficulty: Difficulty = "medium"
    topics: list[str] = Field(min_length=1, max_length=20)
    stem: str = Field(min_length=1, max_length=20000)
    answer_explanation: str = Field(min_length=1, max_length=10000)
    rubric: list[RubricDimension] = Field(min_length=1, max_length=20)
    source_refs: list[SourceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_rubric(self) -> Self:
        if not self.stem.strip() or len({r.id for r in self.rubric}) != len(self.rubric):
            raise ValueError("题干或评分规则非法")
        if len({r.source_id for r in self.source_refs}) != len(self.source_refs):
            raise ValueError("重复引用")
        return self


class ChoiceQuestion(QuestionBase):
    options: list[Option] = Field(min_length=2, max_length=10)

    @model_validator(mode="after")
    def unique_options(self) -> Self:
        if len({o.id for o in self.options}) != len(self.options) or len(
            {o.text.strip().casefold() for o in self.options}
        ) != len(self.options):
            raise ValueError("选项不能重复")
        return self


class SingleChoiceQuestion(ChoiceQuestion):
    type: Literal["single_choice"]
    answer: str

    @model_validator(mode="after")
    def valid_answer(self) -> Self:
        if self.answer not in {o.id for o in self.options}:
            raise ValueError("答案必须属于选项")
        return self


class MultipleChoiceQuestion(ChoiceQuestion):
    type: Literal["multiple_choice"]
    answer: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_answer(self) -> Self:
        if len(set(self.answer)) != len(self.answer) or not set(self.answer) <= {
            o.id for o in self.options
        }:
            raise ValueError("多选答案非法")
        return self


class TrueFalseQuestion(QuestionBase):
    type: Literal["true_false"]
    answer: bool = Field(strict=True)


class ShortAnswerQuestion(QuestionBase):
    type: Literal["short_answer"]
    answer: list[str] = Field(min_length=1)


class CodeTextQuestion(QuestionBase):
    type: Literal["code_text"]
    answer: list[str] = Field(min_length=1)


QuestionSnapshot = Annotated[
    SingleChoiceQuestion
    | MultipleChoiceQuestion
    | TrueFalseQuestion
    | ShortAnswerQuestion
    | CodeTextQuestion,
    Field(discriminator="type"),
]


class SingleAnswer(StrictModel):
    type: Literal["single_choice"]
    option_id: str


class MultipleAnswer(StrictModel):
    type: Literal["multiple_choice"]
    option_ids: list[str]


class BooleanAnswer(StrictModel):
    type: Literal["true_false"]
    value: bool = Field(strict=True)


class TextAnswer(StrictModel):
    type: Literal["short_answer", "code_text"]
    text: str = Field(max_length=30000)


AnswerValue = Annotated[
    SingleAnswer | MultipleAnswer | BooleanAnswer | TextAnswer, Field(discriminator="type")
]


class SetCreate(StrictModel):
    title: str = Field(default="学习练习", min_length=1, max_length=120)
    config: PracticeConfig
    request_key: UUID


class VersionRequest(StrictModel):
    expected_version: int = Field(ge=1)


class SetPatch(VersionRequest):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    config: PracticeConfig | None = None


class PlanRequest(VersionRequest):
    request_key: UUID


class GenerateRequest(PlanRequest):
    plan_version: int = Field(ge=1)
    candidate: Literal["original", "recommended"]
    confirmed_config_digest: str = Field(min_length=64, max_length=64)


class RegenerateRequest(PlanRequest):
    base_revision_id: UUID
    question_id: UUID | None = None


class QuestionEdit(VersionRequest):
    question: QuestionSnapshot


class AttemptCreate(PlanRequest):
    revision_id: UUID


class AnswerSave(VersionRequest):
    answer: AnswerValue
    current_question_id: UUID | None = None


class SubmitRequest(PlanRequest):
    answer_version: int = Field(ge=1)


class RegradeRequest(StrictModel):
    reason: str = Field(min_length=1, max_length=1000)
    request_key: UUID


class RetryRequest(StrictModel):
    request_key: UUID
    input_digest: str = Field(min_length=64, max_length=64)


class ResultRef(StrictModel):
    type: Literal["plan", "revision", "grade"]
    id: UUID
    version: int = Field(ge=1)


class RunView(StrictModel):
    id: UUID
    operation: Literal["plan", "generate", "regenerate", "grade", "regrade"]
    status: Literal["pending", "processing", "cancel_requested", "succeeded", "failed", "cancelled"]
    stage: str
    attempt_count: int
    retryable: bool
    error_key: str | None
    submission_id: UUID | None
    result_ref: ResultRef | None
    request_key: UUID
    input_digest: str


class PlanCandidate(StrictModel):
    config: PracticeConfig
    summary: str
    config_digest: str
    effective_context: dict[str, object]


class PlanView(StrictModel):
    id: UUID
    set_id: UUID
    version: int
    base_set_version: int
    original: PlanCandidate
    recommended: PlanCandidate
    suggestions: list[str]


class SourcePreview(StrictModel):
    source: SourceRef
    available: bool
    evidence: str | None


class RevisionView(StrictModel):
    id: UUID
    set_id: UUID
    version: int
    config: PracticeConfig
    effective_context: dict[str, object]
    questions: list[QuestionSnapshot]
    source_available: bool
    question_feedback: dict[str, Literal["helpful", "unhelpful"] | None] = Field(
        default_factory=dict
    )
    source_mode: Literal["materials", "general"]
    reason: str
    created_at: datetime


class SetView(StrictModel):
    profile_override_fields: list[str] = Field(default_factory=list)
    id: UUID
    title: str
    config: PracticeConfig
    version: int
    current_revision_id: UUID | None
    source_available: bool
    created_at: datetime
    updated_at: datetime


class AnswerView(StrictModel):
    question_id: UUID
    version: int
    answer: AnswerValue


class AnswerEvidence(StrictModel):
    quote: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class DimensionGrade(StrictModel):
    dimension_id: str
    level: Literal["correct", "partial", "incorrect", "absent"]
    evidence: list[AnswerEvidence] = Field(default_factory=list)
    score: float | None = Field(default=None, ge=0)
    max_score: float | None = Field(default=None, gt=0)


class GradePayload(StrictModel):
    level: Literal["correct", "partial", "incorrect"]
    dimensions: list[DimensionGrade] = Field(min_length=1)
    score: float | None = Field(default=None, ge=0)
    max_score: float | None = Field(default=None, gt=0)
    confidence: float = Field(ge=0, le=1)
    missing_points: list[str] = Field(default_factory=list)
    error_reasons: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class GradeView(GradePayload):
    id: UUID
    submission_id: UUID
    version: int
    low_confidence: bool
    feedback: Literal["helpful", "unhelpful"] | None = None
    rubric: list[RubricDimension]
    topics: list[str]
    source_mode: Literal["materials", "general"]
    created_at: datetime


class SubmissionGradeView(StrictModel):
    submission_id: UUID
    question_id: UUID
    answer: AnswerValue
    answer_version: int
    grades: list[GradeView]
    run: RunView | None = None


class AttemptView(StrictModel):
    id: UUID
    set_id: UUID
    revision_id: UUID
    status: Literal["active", "completed"]
    version: int
    current_question_id: UUID | None
    questions: list[QuestionSnapshot]
    answers: list[AnswerView]
    submissions: list[SubmissionGradeView]
    source_available: bool
    question_feedback: dict[str, Literal["helpful", "unhelpful"] | None] = Field(
        default_factory=dict
    )
    started_at: datetime
    completed_at: datetime | None


class SetDetail(SetView):
    revision: RevisionView | None
    attempts: list[AttemptView]


class ReportQuestion(StrictModel):
    question_id: UUID
    topics: list[str]
    submission: SubmissionGradeView | None
    status: Literal["unsubmitted", "ungraded", "correct", "partial", "incorrect"]


class TopicReport(StrictModel):
    topic: str
    correct: int = 0
    partial: int = 0
    incorrect: int = 0
    ungraded: int = 0
    unsubmitted: int = 0
    insufficient_sample: bool = True
    error_reasons: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class ReportView(StrictModel):
    attempt_id: UUID
    status: Literal["active", "completed"]
    total_questions: int
    submitted_count: int
    graded_count: int
    questions: list[ReportQuestion]
    topics: list[TopicReport]
    score: float | None = None
    max_score: float | None = None
    source_mode: Literal["materials", "general"]


class FeedbackRequest(StrictModel):
    revision_id: UUID | None = None
    question_id: UUID | None = None
    grade_id: UUID | None = None
    feedback: Literal["helpful", "unhelpful"] | None

    @model_validator(mode="after")
    def target(self) -> Self:
        if bool(self.grade_id) == bool(self.revision_id and self.question_id):
            raise ValueError("须选择唯一题目或点评")
        if self.grade_id and (self.revision_id or self.question_id):
            raise ValueError("反馈对象只能有一个")
        return self


class FeedbackView(FeedbackRequest):
    id: UUID
