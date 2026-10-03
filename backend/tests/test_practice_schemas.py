from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from xuemian_ai.practice.schemas import AnswerValue, PracticeConfig, QuestionSnapshot
from xuemian_ai.practice.service import config_dump, digest


def test_config_defaults_and_explicit_profile_clearing() -> None:
    config = PracticeConfig(topic="事务")
    assert config.question_count == 5 and config.question_types == {"single_choice": 5}
    assert "target_job" not in config_dump(config)
    explicit = PracticeConfig(topic="事务", target_job=None, target_skills=[])
    assert config_dump(explicit)["target_job"] is None
    assert config_dump(explicit)["target_skills"] == []
    assert config_dump(config)["source_mode"] == "general"


@pytest.mark.parametrize(
    "fields",
    [
        {"question_count": 2},
        {"question_count": 0},
        {"question_types": {"single_choice": -1}},
        {"source_mode": "materials"},
        {"knowledge_base_id": uuid4()},
    ],
)
def test_invalid_configs(fields) -> None:
    with pytest.raises(ValidationError):
        PracticeConfig(**fields)


def test_objective_schema_rejects_invalid_answers_and_duplicate_options() -> None:
    question = {
        "question_id": str(uuid4()),
        "type": "single_choice",
        "stem": "题目",
        "topics": ["事务"],
        "answer_explanation": "解释",
        "rubric": [{"id": "correct", "description": "选择正确答案", "max_score": 1}],
        "options": [{"id": "A", "text": "第一项"}, {"id": "B", "text": "第二项"}],
        "answer": "A",
    }
    assert TypeAdapter(QuestionSnapshot).validate_python(question).answer == "A"
    with pytest.raises(ValidationError):
        TypeAdapter(QuestionSnapshot).validate_python({**question, "answer": "missing"})
    with pytest.raises(ValidationError):
        TypeAdapter(QuestionSnapshot).validate_python(
            {**question, "options": [question["options"][0]] * 2}
        )
    with pytest.raises(ValidationError):
        TypeAdapter(AnswerValue).validate_python({"type": "true_false", "value": "false"})


def test_digest_canonicalizes_mapping_order() -> None:
    assert digest({"a": 1, "b": 2}) == digest({"b": 2, "a": 1})
    assert digest({"a": 1}) != digest({"a": 2})
