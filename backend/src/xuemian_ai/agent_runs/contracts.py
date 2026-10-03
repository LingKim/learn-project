"""并行模块共用的运行快照契约，入队后不能重新选择活动提示词。"""

import hashlib
import json
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class PromptPartSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version_id: UUID
    definition_key: str
    slot: Literal["global", "agent", "task"]
    position: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ContextSourceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    field: str
    source: Literal["request", "selected_asset", "weakness", "profile", "default"]
    reference_id: UUID | None = None
    reference_version: str | None = None
    digest: str | None = None
    disabled: bool = False


class ManagedPromptSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    protocol_version: Literal[1] = 1
    agent_run_id: UUID
    agent_key: Literal["question_generator"] = "question_generator"
    scene_key: Literal["practice_generate"] = "practice_generate"
    root_prompt_version_id: UUID
    composition: list[PromptPartSnapshot]
    contract_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    output_schema_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider: Literal["dashscope"] = "dashscope"
    model: str
    model_parameters: dict[str, Any]
    context_sources: list[ContextSourceSnapshot] = Field(default_factory=list)


class RenderedManagedPrompt(BaseModel):
    """短期内存装配结果；正文不进入 AgentRun、manifest 或普通日志。"""

    model_config = ConfigDict(extra="forbid")
    system_messages: list[str]
    snapshot: ManagedPromptSnapshot
