"""只替换一次简单占位符；用户事实通过 data message 输入，绝不插入 system 指令。"""

import json
import re
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from xuemian_ai.agent_runs.contracts import ContextSourceSnapshot, canonical_hash
from xuemian_ai.core.errors import ValidationAppError
from xuemian_ai.practice.context import PROFILE_FIELDS
from xuemian_ai.practice.schemas import PracticeConfig
from xuemian_ai.prompt_management.registry import VARIABLES
from xuemian_ai.prompt_management.schemas import Variable

TOKEN = re.compile(r"(?<!{){{\s*([a-z][a-z0-9_]*)\s*}}(?!})")


def invalid() -> ValidationAppError:
    return ValidationAppError(
        "模板或合成数据未通过代码契约校验", error_key="PROMPT_TEMPLATE_INVALID"
    )


def bounded_data(value: Any, depth: int = 0) -> None:
    if depth > 8:
        raise invalid()
    if isinstance(value, dict):
        if len(value) > 200 or any(not isinstance(key, str) for key in value):
            raise invalid()
        for item in value.values():
            bounded_data(item, depth + 1)
    elif isinstance(value, list):
        if len(value) > 200:
            raise invalid()
        for item in value:
            bounded_data(item, depth + 1)
    elif value is not None and not isinstance(value, (str, bool, int, float)):
        raise invalid()
    try:
        if depth == 0 and len(json.dumps(value, ensure_ascii=False, allow_nan=False)) > 200000:
            raise invalid()
    except (ValueError, TypeError):
        raise invalid() from None


def validate_template(content: str, variables: list[Variable]) -> None:
    if not content.strip() or len(content) > 20000:
        raise invalid()
    # 变量契约来自代码。管理员可编辑指令，不能把用户事实升级成系统变量。
    if [v.model_dump() for v in variables] != [v.model_dump() for v in VARIABLES]:
        raise invalid()
    remainder = TOKEN.sub("", content)
    if any(marker in remainder for marker in ("{{", "}}", "{%", "%}", "{#", "#}")):
        raise invalid()
    if not set(TOKEN.findall(content)) <= {v.name for v in variables}:
        raise invalid()


def render(content: str, variables: list[Variable], trusted_values: Mapping[str, Any]) -> str:
    validate_template(content, variables)
    names = set(TOKEN.findall(content))
    definitions = {v.name: v for v in variables}
    for name in names:
        rule = definitions[name]
        value = trusted_values.get(name)
        if (
            value is None
            or (rule.type == "string" and not isinstance(value, str))
            or (rule.type == "object" and not isinstance(value, dict))
        ):
            raise invalid()
        bounded_data(value)
        if len(json.dumps(value, ensure_ascii=False)) > rule.max_length:
            raise invalid()
    return TOKEN.sub(
        lambda match: (
            json.dumps(trusted_values[match[1]], ensure_ascii=False)
            if definitions[match[1]].type == "object"
            else str(trusted_values[match[1]])
        ),
        content,
    )


def resolve_fields(
    request: Mapping[str, Any],
    selected_asset: Mapping[str, Any] | None = None,
    weakness: Mapping[str, Any] | None = None,
    profile: Mapping[str, Any] | None = None,
    defaults: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], list[ContextSourceSnapshot]]:
    values: dict[str, Any] = {}
    sources: list[ContextSourceSnapshot] = []
    layers = [
        ("request", request),
        ("selected_asset", selected_asset or {}),
        ("weakness", weakness or {}),
        ("profile", profile or {}),
        ("default", defaults or {}),
    ]
    allowed = set(PROFILE_FIELDS) | {"version", "id"}
    for _, layer in layers:
        if set(layer) - allowed:
            raise invalid()
    for field in PROFILE_FIELDS:
        for name, layer in layers:
            if field not in layer:
                continue
            value = layer[field]
            values[field] = value
            sources.append(
                ContextSourceSnapshot.model_validate(
                    {
                        "field": field,
                        "reference_id": UUID(str(layer["id"]))
                        if layer.get("id") is not None
                        else None,
                        "source": name,
                        "digest": canonical_hash(value),
                        "reference_version": str(layer["version"])
                        if layer.get("version") is not None
                        else None,
                        "disabled": name == "request" and value is None,
                    }
                )
            )
            break
    bounded_data(values)
    try:
        PracticeConfig.model_validate({"topic": "合成上下文校验", **values})
    except ValidationError:
        raise invalid() from None
    return values, sources
