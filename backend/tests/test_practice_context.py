import pytest
from pydantic import BaseModel

from xuemian_ai.core.errors import ValidationAppError
from xuemian_ai.practice.context import ensure_general_topic, resolve_context


class Overrides(BaseModel):
    target_job: str | None = None
    target_skills: list[str] | None = None
    experience_months: int | None = None


def test_presence_fallback_and_profile_not_mutated():
    profile = {"target_job": "Java", "target_skills": ["SQL"], "version": 3}
    context = resolve_context(Overrides(target_skills=[]), profile)
    assert context["values"]["target_job"] == "Java"
    assert context["values"]["target_skills"] == []
    assert context["sources"]["target_skills"] == "explicit"
    assert context["profile_version"] == 3
    assert profile["target_skills"] == ["SQL"]


def test_null_and_zero_are_values_not_omission():
    result = resolve_context(
        {"target_job": None, "experience_months": 0},
        {"target_job": "SQL", "experience_months": 5},
        {"target_job": "Python"},
    )
    assert result["values"]["target_job"] is None
    assert result["values"]["experience_months"] == 0


def test_materials_before_profile_and_missing_profile():
    assert (
        resolve_context({}, {"target_job": "Java"}, {"target_job": "Python"})["values"][
            "target_job"
        ]
        == "Python"
    )
    assert resolve_context({}, None)["profile_version"] is None


def test_empty_general_context_rejected():
    with pytest.raises(ValidationAppError):
        ensure_general_topic({"source_mode": "general"}, resolve_context({}, None))
    ensure_general_topic({"source_mode": "materials"}, resolve_context({}, None))
    ensure_general_topic({"source_mode": "general", "topics": ["SQL"]}, {})


def test_whitespace_is_not_a_general_topic():
    with pytest.raises(ValidationAppError):
        ensure_general_topic(
            {"source_mode": "general", "topic": "   "},
            resolve_context({"target_skills": [" "], "target_job": "\n"}, None),
        )
