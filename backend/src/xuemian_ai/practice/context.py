"""Resolve presence-aware profile context without changing the user's profile."""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from xuemian_ai.core.errors import ValidationAppError

PROFILE_FIELDS = (
    "target_job",
    "experience_months",
    "target_level",
    "target_skills",
    "focus_topics",
    "learning_goal",
    "preferred_language",
)


def resolve_context(
    overrides: Mapping[str, Any] | BaseModel,
    profile: Mapping[str, Any] | None,
    material_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Only absent fields fall back: explicit null/[]/empty text stays cleared."""
    supplied = (
        overrides.model_dump(exclude_unset=True)
        if isinstance(overrides, BaseModel)
        else dict(overrides)
    )
    profile = profile or {}
    material_context = material_context or {}
    values: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for field in PROFILE_FIELDS:
        if field in supplied:
            values[field], sources[field] = supplied[field], "explicit"
        elif field in material_context:
            values[field], sources[field] = material_context[field], "materials"
        else:
            values[field], sources[field] = profile.get(field), "profile"
    return {"values": values, "sources": sources, "profile_version": profile.get("version")}


def ensure_general_topic(config: Mapping[str, Any], context: Mapping[str, Any]) -> None:
    values = context.get("values", context)

    def meaningful(value: Any) -> bool:
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, list):
            return any(meaningful(item) for item in value)
        return False

    if config.get("source_mode") == "general" and not any(
        meaningful(value)
        for value in (
            config.get("topics"),
            config.get("topic"),
            values.get("target_skills"),
            values.get("focus_topics"),
            values.get("target_job"),
            values.get("learning_goal"),
        )
    ):
        raise ValidationAppError("请填写知识点或技能", error_key="PRACTICE_CONFIG_INVALID")
