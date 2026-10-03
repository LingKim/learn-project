from copy import deepcopy
from uuid import uuid4

import pytest

from xuemian_ai.core.errors import UpstreamServiceError, ValidationAppError
from xuemian_ai.document_processing.schemas import EvidenceChunk
from xuemian_ai.practice.generation import prompt_manifest, validate_questions


def question(kind="single_choice"):
    data = dict(
        question_id=str(uuid4()),
        type=kind,
        difficulty="medium",
        topics=["SQL"],
        stem="事务是什么？",
        answer_explanation="事务是操作集合。",
        rubric=[{"id": "accuracy", "description": "准确说明事务", "max_score": 1}],
    )
    if kind in {"single_choice", "multiple_choice"}:
        data["options"] = [{"id": "a", "text": "操作集合"}, {"id": "b", "text": "索引"}]
    data["answer"] = {
        "single_choice": "a",
        "multiple_choice": ["a"],
        "true_false": True,
        "short_answer": ["操作集合"],
        "code_text": ["事务原子性"],
    }[kind]
    data["citation_ids"] = []
    return data


def config(kind="single_choice", mode="general"):
    return dict(source_mode=mode, question_count=1, question_types={kind: 1}, difficulty="medium")


def evidence():
    return EvidenceChunk(
        chunk_id=uuid4(),
        file_id=uuid4(),
        file_name="合成.txt",
        processing_version_id=uuid4(),
        content="事务是操作集合",
        score=0.8,
        source_kind="paragraph",
        page_start=None,
        page_end=None,
        paragraph_start=1,
        paragraph_end=1,
        heading_path=[],
        ocr_confidence=None,
    )


@pytest.mark.parametrize(
    "kind", ["single_choice", "multiple_choice", "true_false", "short_answer", "code_text"]
)
def test_five_types_pass(kind):
    result = validate_questions(
        {"status": "ready", "questions": [question(kind)]}, config(kind), []
    )
    assert result[0]["type"] == kind
    assert result[0]["source_refs"] == []


def test_grounded_mapping_never_contains_source_text():
    item = evidence()
    q = question()
    q["citation_ids"] = [1]
    file_id = str(uuid4())
    result = validate_questions(
        {"status": "ready", "questions": [q]},
        config(mode="materials"),
        [item],
        {str(item.file_id): file_id},
    )
    ref = result[0]["source_refs"][0]
    assert ref["file_id"] == str(item.file_id)
    assert ref["file_asset_id"] == file_id
    assert "content" not in ref


@pytest.mark.parametrize("citations", [[2], [1, 1], [], [True], ["1"]])
def test_illegal_material_citation_rejected(citations):
    q = question()
    q["citation_ids"] = citations
    with pytest.raises(UpstreamServiceError):
        validate_questions(
            {"status": "ready", "questions": [q]}, config(mode="materials"), [evidence()]
        )


@pytest.mark.parametrize(
    "field,value", [("answer", "c"), ("stem", " "), ("rubric", []), ("answer_explanation", " ")]
)
def test_invalid_question_rejected(field, value):
    q = question()
    q[field] = value
    with pytest.raises(UpstreamServiceError):
        validate_questions({"status": "ready", "questions": [q]}, config(), [])


def test_duplicate_and_wrong_distribution_rejected():
    q = question()
    with pytest.raises(UpstreamServiceError):
        validate_questions(
            {"status": "ready", "questions": [q, deepcopy(q)]},
            dict(config(), question_count=2, question_types={"single_choice": 2}),
            [],
        )
    with pytest.raises(UpstreamServiceError):
        validate_questions({"status": "ready", "questions": [q]}, config("true_false"), [])


def test_insufficient_never_falls_back_to_general():
    with pytest.raises(ValidationAppError):
        validate_questions(
            {"status": "evidence_insufficient", "questions": []},
            config(mode="materials"),
            [evidence()],
        )
    with pytest.raises(ValidationAppError):
        validate_questions(
            {"status": "ready", "questions": [question()]}, config(mode="materials"), []
        )


def test_manifest_is_reproducible_and_operation_specific():
    assert prompt_manifest("generate", {}) == prompt_manifest("generate", {})
    assert prompt_manifest("generate", {})["sha256"] != prompt_manifest("grade", {})["sha256"]


def test_provider_schema_owns_structure_and_excludes_server_metadata():
    from xuemian_ai.practice.generation import generation_schema

    schema = generation_schema()
    for kind in [
        "SingleChoiceQuestion",
        "MultipleChoiceQuestion",
        "TrueFalseQuestion",
        "ShortAnswerQuestion",
        "CodeTextQuestion",
    ]:
        definition = schema["$defs"][kind]
        assert "source_refs" not in definition["properties"]
        assert "question_id" not in definition["properties"]
        assert definition["properties"]["citation_ids"]["items"]["type"] == "integer"
        assert definition["properties"]["topics"]["items"]["type"] == "string"
        assert set(definition["required"]) == set(definition["properties"])


async def test_real_provider_uses_json_schema_and_sanitizes_provider_failures():
    import json
    from unittest.mock import AsyncMock, patch

    from langchain_core.messages import AIMessage

    from xuemian_ai.core.config import get_settings
    from xuemian_ai.practice.generation import QwenPracticeProvider

    with patch("xuemian_ai.practice.generation.ChatOpenAI") as model:
        model.return_value.ainvoke = AsyncMock(
            return_value=AIMessage(
                content=json.dumps({"status": "ready", "questions": []}),
                response_metadata={"finish_reason": "stop"},
            )
        )
        provider = QwenPracticeProvider(get_settings())
        await provider.invoke("generate", {"config": config()})
        kwargs = model.return_value.ainvoke.call_args.kwargs
        assert kwargs["response_format"]["type"] == "json_schema"
        assert kwargs["response_format"]["json_schema"]["strict"] is True
        assert model.call_args.kwargs["extra_body"]["enable_thinking"] is False
        model.return_value.ainvoke.side_effect = RuntimeError("synthetic private provider body")
        with pytest.raises(UpstreamServiceError) as failure:
            await provider.invoke("generate", {"config": config()})
        assert "private provider" not in str(failure.value)
        assert failure.value.error_key == "PRACTICE_PROVIDER_UNAVAILABLE"


def test_normalized_duplicate_options_fail_before_publication():
    q = question()
    q["options"] = [{"id": "a", "text": "集合！"}, {"id": "b", "text": "集合"}]
    with pytest.raises(UpstreamServiceError) as failure:
        validate_questions({"status": "ready", "questions": [q]}, config(), [])
    assert failure.value.error_key == "PRACTICE_GENERATION_INVALID"
