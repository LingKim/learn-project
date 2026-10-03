"""Deterministic objective grading and strict subjective publication gates."""

import math
import re
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError

from xuemian_ai.core.errors import UpstreamServiceError, ValidationAppError
from xuemian_ai.practice.schemas import AnswerValue, GradePayload, QuestionSnapshot


def _mapping(value: dict[str, Any] | BaseModel) -> dict[str, Any]:
    return value.model_dump(mode="json") if isinstance(value, BaseModel) else value


def grade_objective(
    question: dict[str, Any] | BaseModel,
    answer: dict[str, Any] | BaseModel,
) -> GradePayload:
    q: QuestionSnapshot = TypeAdapter(QuestionSnapshot).validate_python(_mapping(question))
    a: AnswerValue = TypeAdapter(AnswerValue).validate_python(_mapping(answer))
    if q.type != a.type or q.type not in {"single_choice", "multiple_choice", "true_false"}:
        raise ValidationAppError(error_key="PRACTICE_CONFIG_INVALID")
    reasons: list[str] = []
    if q.type == "single_choice" and a.type == "single_choice":
        if a.option_id not in {option.id for option in q.options}:
            raise ValidationAppError("答案选项无效", error_key="PRACTICE_CONFIG_INVALID")
        correct = a.option_id == q.answer
        if not correct:
            reasons = ["错选：所选选项与标准答案不符"]
    elif q.type == "multiple_choice" and a.type == "multiple_choice":
        selected, expected = set(a.option_ids), set(q.answer)
        if len(selected) != len(a.option_ids) or not selected <= {o.id for o in q.options}:
            raise ValidationAppError("答案选项无效", error_key="PRACTICE_CONFIG_INVALID")
        correct = selected == expected
        if expected - selected:
            reasons.append("漏选：未选择全部正确选项")
        if selected - expected:
            reasons.append("多选或错选：包含不正确选项")
    elif q.type == "true_false" and a.type == "true_false":
        correct = a.value is q.answer
        if not correct:
            reasons = ["判断与标准答案不符"]
    else:
        raise ValidationAppError(error_key="PRACTICE_CONFIG_INVALID")
    full_rules = all(r.max_score is not None for r in q.rubric)
    dimensions: list[dict[str, Any]] = [
        {
            "dimension_id": r.id,
            "level": "correct" if correct else "incorrect",
            "evidence": [],
            "score": (r.max_score if correct else 0) if full_rules else None,
            "max_score": r.max_score if full_rules else None,
        }
        for r in q.rubric
    ]
    maximum = sum(r.max_score or 0 for r in q.rubric) if full_rules else None
    return GradePayload.model_validate(
        {
            "level": "correct" if correct else "incorrect",
            "dimensions": dimensions,
            "score": (maximum if correct else 0) if full_rules else None,
            "max_score": maximum,
            "confidence": 1,
            "missing_points": [],
            "error_reasons": reasons,
            "suggestions": [q.answer_explanation],
        }
    )


def validate_subjective_grade(
    raw: dict[str, Any],
    question: dict[str, Any] | BaseModel,
    answer: dict[str, Any] | BaseModel,
) -> GradePayload:
    try:
        q: QuestionSnapshot = TypeAdapter(QuestionSnapshot).validate_python(_mapping(question))
        a: AnswerValue = TypeAdapter(AnswerValue).validate_python(_mapping(answer))
        if q.type not in {"short_answer", "code_text"} or a.type != q.type:
            raise ValueError("not subjective")
        assert a.type in {"short_answer", "code_text"}
        grade = GradePayload.model_validate(raw)
        rules = {r.id: r for r in q.rubric}
        ids = [d.dimension_id for d in grade.dimensions]
        if len(ids) != len(set(ids)) or set(ids) != set(rules):
            raise ValueError("unknown or omitted dimension")
        numeric = all(r.max_score is not None for r in q.rubric)
        for dimension in grade.dimensions:
            rule = rules[dimension.dimension_id]
            if dimension.level != "absent" and not dimension.evidence:
                raise ValueError("missing evidence")
            if dimension.level == "absent" and dimension.evidence:
                raise ValueError("absent has quote")
            if dimension.level == "absent" and not grade.missing_points:
                raise ValueError("missing point unreported")
            for evidence in dimension.evidence:
                if (
                    not evidence.quote
                    or evidence.start >= evidence.end
                    or evidence.end > len(a.text)
                    or a.text[evidence.start : evidence.end] != evidence.quote
                ):
                    raise ValueError("fabricated answer evidence")
            if numeric:
                if (
                    dimension.score is None
                    or dimension.max_score != rule.max_score
                    or not math.isfinite(dimension.score)
                    or dimension.score > (rule.max_score or 0)
                ):
                    raise ValueError("invalid dimension score")
            elif dimension.score is not None or dimension.max_score is not None:
                raise ValueError("incomplete numerical rubric")
        if numeric:
            for d in grade.dimensions:
                if d.level in {"incorrect", "absent"} and d.score != 0:
                    raise ValueError("incorrect dimension cannot receive credit")
                if d.level == "correct" and d.score != d.max_score:
                    raise ValueError("correct dimension must match complete rubric")
            maximum = sum(r.max_score or 0 for r in q.rubric)
            score = sum(d.score or 0 for d in grade.dimensions)
            if (
                grade.score is None
                or grade.max_score != maximum
                or not math.isfinite(grade.score)
                or not math.isclose(grade.score, score)
            ):
                raise ValueError("invalid aggregate")
        elif grade.score is not None or grade.max_score is not None:
            raise ValueError("incomplete numerical rubric")
        if grade.level == "correct" and any(d.level != "correct" for d in grade.dimensions):
            raise ValueError("overall correct contradicts dimension findings")
        if grade.level == "incorrect" and all(d.level == "correct" for d in grade.dimensions):
            raise ValueError("overall incorrect contradicts complete correctness")
        if not grade.suggestions or any(not s.strip() for s in grade.suggestions):
            raise ValueError("missing suggestions")
        if not math.isfinite(grade.confidence):
            raise ValueError("invalid confidence")
        if q.type == "code_text":
            prose = " ".join(grade.suggestions + grade.error_reasons + grade.missing_points)
            if re.search(
                r"(?:已|实际|成功)(?:编译|执行|运行|通过测试)|测试(?:已)?通过|"
                r"(?:编译|执行|运行)(?:已|均|全部)?(?:成功|通过)|"
                r"测试(?:均|全部)?(?:已|已经)?通过|"
                r"\b(?:compiled successfully|tests? (?:have |has )?passed|"
                r"compilation succeeded|executed successfully)\b",
                prose,
                re.IGNORECASE,
            ):
                raise ValueError("claims code execution")
        return grade
    except (ValueError, TypeError, ValidationError):
        raise UpstreamServiceError(
            "点评证据或评分规则未通过校验", error_key="PRACTICE_GRADE_INVALID"
        ) from None
