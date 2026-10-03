from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from xuemian_ai.learning.result_sources import TraceMetadata

Category = Literal[
    "not_found",
    "irrelevant_source",
    "wrong_answer",
    "wrong_citation",
    "outdated_content",
    "slow",
    "other",
]
CaseStatus = Literal["submitted", "triaging", "waiting_user", "investigating", "resolved", "closed"]
GrantStatus = Literal["pending", "active", "expired", "revoked", "rejected"]
GrantField = Literal["query", "final_output", "final_citations", "candidate_excerpts"]
ReplayMode = Literal["fts_only", "vector_only", "hybrid_only", "without_rerank", "full"]
ResolutionCode = Literal[
    "parsing_gap",
    "stale_index",
    "fts_filter",
    "vector_recall",
    "fusion",
    "rerank",
    "evidence_gate",
    "generation",
    "citation",
    "source_outdated",
    "latency",
    "not_reproduced",
    "user_expectation",
    "unknown",
]
Nonblank = Annotated[str, Field(min_length=1, max_length=4000)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, from_attributes=True)


class VersionRequest(Contract):
    expected_version: int = Field(ge=1)


class CaseCreate(Contract):
    source_type: Literal["learning_turn"] = "learning_turn"
    source_id: UUID
    trace_id: UUID
    request_key: UUID
    category: Category
    description: Nonblank
    expected_result: str | None = Field(default=None, max_length=2000)
    basic_access_confirmed: Literal[True]


class MessageCreate(VersionRequest):
    content: Nonblank


class AdminMessageCreate(MessageCreate):
    visibility: Literal["user", "admin"]


class AssignmentRequest(VersionRequest):
    assignee_id: UUID | None = None


class TransitionRequest(VersionRequest):
    status: CaseStatus
    resolution_code: ResolutionCode | None = None
    resolution_summary: str | None = Field(default=None, min_length=1, max_length=2000)
    replay_id: UUID | None = None
    deterministic_error_code: Literal["TRACE_INCOMPLETE", "SOURCE_UNAVAILABLE"] | None = None

    @model_validator(mode="after")
    def resolution_required(self) -> "TransitionRequest":
        if self.status == "resolved" and (
            self.resolution_code is None or self.resolution_summary is None
        ):
            raise ValueError("解决工单必须填写归因和公开结论")
        return self


class AccessRequest(VersionRequest):
    reason: str = Field(min_length=1, max_length=1000)
    chunk_ids: list[UUID] = Field(min_length=1, max_length=64)
    duration_days: int = Field(default=30, ge=1, le=30)

    @field_validator("chunk_ids")
    @classmethod
    def unique_chunks(cls, value: list[UUID]) -> list[UUID]:
        return list(dict.fromkeys(value))


class GrantDecision(VersionRequest):
    expected_grant_version: int = Field(ge=1)
    approved: bool


class GrantRevoke(VersionRequest):
    expected_grant_version: int = Field(ge=1)


class SnapshotRequest(Contract):
    grant_id: UUID
    expected_grant_version: int = Field(ge=1)
    fields: list[GrantField] = Field(min_length=1, max_length=4)


class ReplayRequest(VersionRequest):
    grant_id: UUID
    expected_grant_version: int = Field(ge=1)
    mode: ReplayMode
    target_chunk_ids: list[UUID] = Field(default_factory=list, max_length=64)


class CaseView(Contract):
    id: UUID
    case_number: str
    user_id: UUID
    source_type: Literal["learning_turn"]
    source_id: UUID
    trace_id: UUID
    category: Category
    status: CaseStatus
    version: int
    strategy_version: str
    assignee_id: UUID | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    closed_at: datetime | None
    resolution_code: ResolutionCode | None
    resolution_summary: str | None


class GrantView(Contract):
    id: UUID
    version: int
    status: GrantStatus
    fields: list[GrantField]
    chunk_ids: list[UUID]
    reason: str
    requester_id: UUID | None
    expires_at: datetime
    confirmed_at: datetime | None
    revoked_at: datetime | None


class EventView(Contract):
    id: UUID
    action: str
    visibility: Literal["user", "admin"]
    actor_id: UUID | None
    version: int
    content: str | None
    created_at: datetime


class UserCaseDetail(CaseView):
    description: str | None
    expected_result: str | None
    events: list[EventView]
    grants: list[GrantView]


class AuditView(Contract):
    action: str
    outcome: str
    reason_code: str | None
    actor_id: UUID | None
    fields: list[GrantField]
    occurred_at: datetime


class RankingEntry(Contract):
    chunk_id: UUID
    rank: int
    score: float


class RecordedStageMetadata(Contract):
    stage: str
    candidate_count: int
    count: int | None
    elapsed_ms: int | None


class ReplayView(Contract):
    id: UUID
    mode: ReplayMode
    status: Literal["succeeded", "failed"]
    strategy_version: str
    ranking: list[RankingEntry]
    final_chunk_ids: list[UUID]
    metrics: dict[str, float | None]
    comparison_kind: Literal["recorded_candidates_offline"]
    independent_latency_ms: None = None
    causal_claim: Literal[False] = False
    note: str
    recorded_stage_metadata: list[RecordedStageMetadata]
    error_key: str | None = None
    created_at: datetime


class AdminCaseDetail(CaseView):
    trace: TraceMetadata | None
    source_error: str | None
    grants: list[GrantView]
    events: list[EventView]
    replays: list[ReplayView]
    audits: list[AuditView]


class SnapshotView(Contract):
    case_id: UUID
    grant_id: UUID
    grant_version: int
    expires_at: datetime
    values: dict[str, Any]
    description: str | None = None
    expected_result: str | None = None


class QualityOverview(Contract):
    counts_by_status: dict[str, int]
    counts_by_category: dict[str, int]
    counts_by_source: dict[str, int]
    counts_by_strategy: dict[str, int]
    daily_counts: dict[str, int]
    first_response_seconds: dict[str, float | None]
    resolution_seconds: dict[str, float | None]
    backlog_seconds: dict[str, float | None]
    error_counts: dict[str, int]
