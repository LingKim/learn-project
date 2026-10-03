"""Targeted model output must retain the exact single concept in the frozen config."""

from xuemian_ai.practice.generation import generation_schema


def test_targeted_schema_constrains_each_question_to_one_exact_topic() -> None:
    config = {
        "topic": "事务原子性",
        "learning_target": {"kind": "weakness", "id": "target", "version": 1},
        "question_types": {"single_choice": 3},
    }
    schema = generation_schema(config)
    for definition in schema["$defs"].values():
        properties = definition.get("properties", {})
        if "stem" in properties:
            assert properties["topics"] == {
                "type": "array",
                "minItems": 1,
                "maxItems": 1,
                "items": {"type": "string", "enum": ["事务原子性"]},
            }
    assert len(schema["properties"]["questions"]["properties"]) == 3


def test_ordinary_practice_schema_keeps_flexible_topic_coverage() -> None:
    schema = generation_schema({"topic": "数据库", "question_types": {"short_answer": 2}})
    topic_schema = schema["$defs"]["ShortAnswerQuestion"]["properties"]["topics"]
    assert "enum" not in topic_schema["items"]
