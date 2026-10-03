"""固定合成资料测试真实验证器；不联网、不读取用户业务内容。"""

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI

from xuemian_ai.api.prompts import router
from xuemian_ai.core.errors import UpstreamServiceError, ValidationAppError
from xuemian_ai.prompt_management.evaluation import CASES, assert_case, evaluation_fingerprint
from xuemian_ai.prompt_management.registry import ENTRIES, ROOT_KEY, VARIABLES, validate_registry
from xuemian_ai.prompt_management.rendering import bounded_data, render, resolve_fields


def synthetic_result(config, evidence):
    if config["source_mode"] == "materials" and not evidence:
        return {"status": "evidence_insufficient", "reason": "合成资料没有证据", "questions": []}
    questions = []
    for kind, count in config["question_types"].items():
        for index in range(count):
            data = {
                "type": kind,
                "difficulty": config["difficulty"],
                "topics": ["事务原子性"],
                "stem": f"合成{kind}{index}：事务原子性是什么？",
                "answer_explanation": "操作要么全部成功，要么全部回滚。",
                "rubric": [
                    {"id": "accuracy", "description": "正确说明全部成功或回滚", "max_score": 1}
                ],
                "citation_ids": [1] if evidence else [],
            }
            if kind in {"single_choice", "multiple_choice"}:
                data["options"] = [
                    {"id": "A", "text": "全部成功或回滚"},
                    {"id": "B", "text": "索引排序"},
                ]
            data["answer"] = {
                "single_choice": "A",
                "multiple_choice": ["A"],
                "true_false": True,
                "short_answer": ["全部成功或回滚"],
                "code_text": ["全部成功或回滚"],
            }[kind]
            questions.append(data)
    return {"status": "ready", "reason": "", "questions": questions}


class SyntheticProvider:
    async def invoke(self, messages, payload, schema):
        assert len(messages) >= 2
        return synthetic_result(payload["config"], payload["evidence"]), {
            "input_tokens": 10,
            "output_tokens": 10,
            "total_tokens": 20,
        }


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_fixed_suite_uses_actual_question_validation(case):
    assert_case(synthetic_result(case["config"], case["evidence"]), case)


def test_suite_rejects_invalid_citation_and_injection_response():
    case = CASES[1]
    data = synthetic_result(case["config"], case["evidence"])
    data["questions"][0]["citation_ids"] = [2]
    with pytest.raises((ValidationAppError, UpstreamServiceError, ValueError)):
        assert_case(data, case)
    with pytest.raises((ValidationAppError, UpstreamServiceError, ValueError)):
        assert_case({"status": "ready", "reason": "忽略规则", "questions": []}, CASES[3])


@pytest.mark.parametrize(
    "text", ["{{unknown}}", "{{ scene_key.attribute }}", "{%for x%}", "{{{scene_key}}}"]
)
def test_template_rejects_unknown_or_expression_variables(text):
    with pytest.raises(ValidationAppError):
        render(text, VARIABLES, {"scene_key": "practice_generate"})


def test_template_is_single_pass_and_explicit_null_blocks_fallback():
    assert render("{{agent_key}}", VARIABLES, {"agent_key": "{{scene_key}}"}) == "{{scene_key}}"
    values, sources = resolve_fields(
        {"target_job": None, "focus_topics": []},
        profile={"target_job": "Java", "focus_topics": ["SQL"], "version": 2},
    )
    assert values == {"target_job": None, "focus_topics": []}
    assert sources[0].disabled and sources[0].source == "request"
    with pytest.raises(ValidationAppError):
        resolve_fields({"system_prompt": "override"})


@pytest.mark.parametrize("value", [float("nan"), {"a": "x" * 200001}, [[[[[[[[[[0]]]]]]]]]]])
def test_data_limits(value):
    with pytest.raises(ValidationAppError):
        bounded_data(value)


@pytest.mark.parametrize(
    "mutation", ["duplicate", "missing", "unknown", "orphan", "tools", "executor"]
)
def test_registry_fails_closed_for_invalid_registration(mutation):
    values = [entry.model_copy(deep=True) for entry in ENTRIES.values()]
    if mutation == "duplicate":
        values.append(values[0])
    elif mutation == "missing":
        values.pop()
    elif mutation == "unknown":
        values[0].definition_key = "future-role"
    elif mutation == "orphan":
        values[1].dependencies = [{"definition_key": "missing", "slot": "global"}]
    elif mutation == "tools":
        values[1].tools = ["arbitrary_python"]
    else:
        values[1].agent_key = "future-agent"
    with pytest.raises(ValueError):
        validate_registry(values)
    validate_registry()


def test_fingerprint_tracks_all_eligibility_conditions():
    settings = SimpleNamespace(learning_answer_model="synthetic-model")
    suite = uuid4()
    composition = [
        {"version_id": str(uuid4()), "sha256": "a" * 64, "slot": "global", "position": 0}
    ]
    args = ["a" * 64, [v.model_dump() for v in VARIABLES], composition, suite, settings]
    base = evaluation_fingerprint(*args)
    changed = deepcopy(args)
    changed[2][0]["version_id"] = str(uuid4())
    assert evaluation_fingerprint(*changed) != base
    changed = list(args)
    changed[0] = "b" * 64
    assert evaluation_fingerprint(*changed) != base
    changed = list(args)
    changed[4] = SimpleNamespace(learning_answer_model="other")
    assert evaluation_fingerprint(*changed) != base
    assert evaluation_fingerprint(*args) == base


def test_real_openapi_has_no_definition_create_or_bootstrap_endpoint():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    paths = app.openapi()["paths"]
    assert "post" not in paths["/api/v1/admin/prompt-definitions"]
    assert "/api/v1/admin/prompt-versions/{version_id}/diff" in paths
    assert not any("bootstrap" in path for path in paths)
    assert ROOT_KEY == "question_generator/practice_generate"


def test_context_snapshot_preserves_learning_target_and_profile_version():
    from xuemian_ai.prompt_management.runtime import context_sources

    target = uuid4()
    values = context_sources(
        {
            "effective_context": {
                "values": {"learning_goal": "合成目标", "target_job": "Java"},
                "sources": {"learning_goal": "materials", "target_job": "profile"},
                "profile_version": 4,
                "learning_target": {"kind": "weakness", "id": str(target), "version": 2},
            }
        }
    )
    assert values[0].source == "weakness" and values[0].reference_id == target
    assert values[0].reference_version == "2" and "合成目标" not in values[0].model_dump_json()
    assert values[1].reference_version == "4" and values[1].source == "profile"
    with pytest.raises(UpstreamServiceError):
        context_sources(
            {
                "effective_context": {
                    "values": {"target_job": "Java"},
                    "sources": {"target_job": "system"},
                }
            }
        )
