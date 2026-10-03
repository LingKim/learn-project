"""注册表只描述已经实际运行的出题能力，数据库正文不能创造工具或执行器。"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from xuemian_ai.agent_runs.contracts import canonical_hash
from xuemian_ai.core.errors import ValidationAppError
from xuemian_ai.practice.generation import PROMPT_PARTS, GeneratedQuestions
from xuemian_ai.practice.schemas import PracticeConfig, QuestionSnapshot
from xuemian_ai.prompt_management.schemas import RegistryEntryView, Variable

ROOT_KEY = "question_generator/practice_generate"
GLOBAL_KEY = "practice_global"
MODEL_PARAMETERS: dict[str, Any] = {"temperature": 0, "enable_thinking": False}


class PracticeInputContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config: PracticeConfig
    effective_context: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=8)


VARIABLES = [
    Variable(name="agent_key", type="string", max_length=64),
    Variable(name="scene_key", type="string", max_length=64),
]
CONTRACT_SHA256 = canonical_hash(
    {
        "input": PracticeInputContext.model_json_schema(),
        "output": GeneratedQuestions.model_json_schema(),
        "questions": TypeAdapter(QuestionSnapshot).json_schema(),
        "tools": [],
        "system_variables": [v.model_dump() for v in VARIABLES],
    }
)

ENTRIES = {
    GLOBAL_KEY: RegistryEntryView(
        definition_key=GLOBAL_KEY,
        agent_key="shared",
        scene_key="global_behavior",
        template_kind="shared",
        display_name="练习公共行为规则",
        description="由真实出题场景依赖的消息信任边界、JSON和用户事实约束。",
        variables=VARIABLES,
        contract_sha256=CONTRACT_SHA256,
        dependencies=[],
        tools=[],
    ),
    ROOT_KEY: RegistryEntryView(
        definition_key=ROOT_KEY,
        agent_key="question_generator",
        scene_key="practice_generate",
        template_kind="task",
        display_name="练习题目生成",
        description="按已确认配置生成五种题型、答案及评分规则，工具权限为空。",
        variables=VARIABLES,
        contract_sha256=CONTRACT_SHA256,
        dependencies=[{"definition_key": GLOBAL_KEY, "slot": "global"}],
        tools=[],
    ),
}
BOOTSTRAP_CONTENT = {GLOBAL_KEY: PROMPT_PARTS[0][2], ROOT_KEY: PROMPT_PARTS[2][2]}


def entry(key: str) -> RegistryEntryView:
    if key not in ENTRIES:
        raise ValidationAppError("场景未注册", error_key="PROMPT_SCENE_UNREGISTERED")
    return ENTRIES[key]


def model_configuration(settings: Any) -> dict[str, Any]:
    return {
        "provider": "dashscope",
        "model": settings.learning_answer_model,
        "parameters": dict(MODEL_PARAMETERS),
    }


def validate_registry(entries: list[RegistryEntryView] | None = None) -> None:
    """启动时核对真实执行入口、无工具权限及固定依赖；错误注册直接阻止启动。"""
    values = list(ENTRIES.values()) if entries is None else entries
    indexed = {value.definition_key: value for value in values}
    if len(indexed) != len(values) or set(indexed) != {GLOBAL_KEY, ROOT_KEY}:
        raise ValueError("prompt registry has duplicate, missing or unknown definitions")
    for key, value in indexed.items():
        expected = ENTRIES[key]
        if value.model_dump() != expected.model_dump():
            raise ValueError("prompt registry does not match the real practice executor contract")
        for dependency in value.dependencies:
            if dependency["definition_key"] not in indexed or dependency["definition_key"] == key:
                raise ValueError("prompt registry has orphan or cyclic dependencies")
    if not MODEL_PARAMETERS == {"temperature": 0, "enable_thinking": False}:
        raise ValueError("prompt model policy does not match the real provider")
