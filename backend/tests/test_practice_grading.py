from copy import deepcopy

import pytest
from test_practice_generation import question

from xuemian_ai.core.errors import UpstreamServiceError, ValidationAppError
from xuemian_ai.practice.grading import grade_objective, validate_subjective_grade


def clean_question(kind):
    q = question(kind)
    q.pop("citation_ids")
    return q


def grade():
    return {
        "level": "correct",
        "dimensions": [
            {
                "dimension_id": "accuracy",
                "level": "correct",
                "evidence": [{"quote": "事务", "start": 0, "end": 2}],
                "score": 1,
                "max_score": 1,
            }
        ],
        "score": 1,
        "max_score": 1,
        "confidence": 0.65,
        "suggestions": ["补充原子性示例"],
    }


def test_multiple_choice_order_and_exact_match():
    q = clean_question("multiple_choice")
    q["answer"] = ["a", "b"]
    assert grade_objective(q, {"type": "multiple_choice", "option_ids": ["b", "a"]}).score == 1
    partial = grade_objective(q, {"type": "multiple_choice", "option_ids": ["a"]})
    assert partial.score == 0
    assert partial.level == "incorrect"
    assert "漏选" in partial.error_reasons[0]
    with pytest.raises(ValidationAppError):
        grade_objective(q, {"type": "multiple_choice", "option_ids": ["a", "a"]})


@pytest.mark.parametrize(
    "kind,answer,correct",
    [
        ("single_choice", {"type": "single_choice", "option_id": "a"}, True),
        ("single_choice", {"type": "single_choice", "option_id": "b"}, False),
        ("true_false", {"type": "true_false", "value": True}, True),
        ("true_false", {"type": "true_false", "value": False}, False),
    ],
)
def test_objective(kind, answer, correct):
    assert (grade_objective(clean_question(kind), answer).level == "correct") is correct


def test_incomplete_rule_never_exposes_score():
    q = clean_question("single_choice")
    q["rubric"][0]["max_score"] = None
    g = grade_objective(q, {"type": "single_choice", "option_id": "a"})
    assert g.score is None and g.dimensions[0].score is None


def test_subjective_verifiable_evidence_and_low_confidence():
    result = validate_subjective_grade(
        grade(), clean_question("short_answer"), {"type": "short_answer", "text": "事务是操作集合"}
    )
    assert result.confidence == 0.65


@pytest.mark.parametrize("change", ["quote", "offset", "unknown", "over", "total", "no_evidence"])
def test_invalid_subjective_never_publishes(change):
    raw = deepcopy(grade())
    d = raw["dimensions"][0]
    if change == "quote":
        d["evidence"][0]["quote"] = "原子性"
    elif change == "offset":
        d["evidence"][0]["end"] = 99
    elif change == "unknown":
        d["dimension_id"] = "fake"
    elif change == "over":
        d["score"] = 2
    elif change == "total":
        raw["score"] = 0
    else:
        d["evidence"] = []
    with pytest.raises(UpstreamServiceError):
        validate_subjective_grade(
            raw, clean_question("short_answer"), {"type": "short_answer", "text": "事务是操作集合"}
        )


def test_absent_points_do_not_invent_answer_quotes():
    raw = grade()
    raw.update(level="incorrect", score=0, missing_points=["absent: 未说明原子性"])
    raw["dimensions"][0].update(level="absent", evidence=[], score=0)
    validate_subjective_grade(
        raw, clean_question("short_answer"), {"type": "short_answer", "text": "不知道"}
    )


@pytest.mark.parametrize("numeric", [True, False])
@pytest.mark.parametrize("overall,dimension", [("correct", "incorrect"), ("incorrect", "correct")])
def test_overall_grade_cannot_contradict_dimension_findings(numeric, overall, dimension):
    raw = grade()
    question = clean_question("short_answer")
    raw["level"] = overall
    raw["dimensions"][0]["level"] = dimension
    raw["score"] = raw["dimensions"][0]["score"] = 0 if dimension == "incorrect" else 1
    if not numeric:
        question["rubric"][0]["max_score"] = None
        raw["score"] = raw["max_score"] = None
        raw["dimensions"][0]["score"] = raw["dimensions"][0]["max_score"] = None
    with pytest.raises(UpstreamServiceError):
        validate_subjective_grade(raw, question, {"type": "short_answer", "text": "事务"})


def test_partial_numeric_rules_reject_model_score():
    q = clean_question("short_answer")
    q["rubric"][0]["max_score"] = None
    with pytest.raises(UpstreamServiceError):
        validate_subjective_grade(grade(), q, {"type": "short_answer", "text": "事务"})


@pytest.mark.parametrize(
    "claim",
    [
        "测试通过",
        "编译成功，运行成功，所有单元测试均已通过。",
        "Compilation succeeded and all tests have passed.",
    ],
)
def test_code_text_cannot_claim_execution(claim):
    raw = grade()
    raw["suggestions"] = [claim]
    with pytest.raises(UpstreamServiceError):
        validate_subjective_grade(
            raw, clean_question("code_text"), {"type": "code_text", "text": "事务"}
        )


def test_absent_dimension_cannot_receive_credit():
    raw = grade()
    raw["level"] = "incorrect"
    raw["dimensions"][0].update(level="absent", evidence=[])
    raw["missing_points"] = ["absent: 缺失要点"]
    with pytest.raises(UpstreamServiceError):
        validate_subjective_grade(
            raw, clean_question("short_answer"), {"type": "short_answer", "text": "事务"}
        )


def test_answer_spans_offsets_are_computed_from_unicode_input():
    from xuemian_ai.practice.generation import answer_spans

    text = "事务要么全部成功，要么全部回滚。\n支持😀。"
    spans = answer_spans(text)
    assert all(text[s["start"] : s["end"]] == s["quote"] for s in spans)
    assert any(s["quote"] == text and s["end"] == len(text) for s in spans)


async def test_provider_resolves_only_known_answer_spans():
    import json
    from unittest.mock import AsyncMock, patch

    from langchain_core.messages import AIMessage

    from xuemian_ai.core.config import get_settings
    from xuemian_ai.practice.generation import QwenPracticeProvider

    q = clean_question("short_answer")
    payload = {"question": q, "answer": {"type": "short_answer", "text": "事务"}}
    raw = grade()
    raw["dimensions"][0]["evidence"] = [{"span_id": 0}]
    with patch("xuemian_ai.practice.generation.ChatOpenAI") as model:
        model.return_value.ainvoke = AsyncMock(
            return_value=AIMessage(
                content=json.dumps(raw), response_metadata={"finish_reason": "stop"}
            )
        )
        result = await QwenPracticeProvider(get_settings()).invoke("grade", payload)
        quote = result["dimensions"][0]["evidence"][0]
        assert quote == {"quote": "事务", "start": 0, "end": 2}
        validate_subjective_grade(result, q, payload["answer"])
        raw["dimensions"][0]["evidence"] = [{"span_id": 99}]
        model.return_value.ainvoke.return_value = AIMessage(
            content=json.dumps(raw), response_metadata={"finish_reason": "stop"}
        )
        with pytest.raises(UpstreamServiceError) as failure:
            await QwenPracticeProvider(get_settings()).invoke("grade", payload)
        assert failure.value.error_key == "PRACTICE_GRADE_INVALID"


def test_subjective_schema_requires_evidence_or_explicit_absent():
    from xuemian_ai.practice.generation import subjective_provider_schema

    schema = subjective_provider_schema(clean_question("short_answer"), {"text": "事务"})
    assert schema["$defs"]["DimensionGrade"]["properties"]["evidence"]["minItems"] == 1
    assert schema["$defs"]["AbsentDimension"]["properties"]["evidence"]["maxItems"] == 0
    assert schema["$defs"]["AbsentDimension"]["properties"]["level"]["const"] == "absent"
    assert schema["$defs"]["SpanEvidence"]["properties"]["span_id"]["enum"] == [0]
