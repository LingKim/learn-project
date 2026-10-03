from copy import deepcopy
from uuid import uuid4

import pytest
from test_practice_generation import evidence

from xuemian_ai.core.errors import UpstreamServiceError, ValidationAppError
from xuemian_ai.learning_assets.generation import (
    audit_passages,
    audit_schema,
    generation_schema,
    prompt_manifest,
    validate_audit,
    validate_card,
)


def card(citations=None):
    return {
        "status": "ready",
        "reason": "",
        "card": {
            "concept": "原子性表示事务整体提交或整体撤销。",
            "applications": ["转账的扣款与入账一起提交。"],
            "principles": ["失败时回滚此前尚未提交的变更。"],
            "examples": [{"title": "转账", "content": "入账失败则撤销扣款。"}],
            "misconceptions": ["原子性不等于事务彼此隔离。"],
            "exercises": [
                {"question": "转账入账失败如何处理？", "self_check_points": ["回滚扣款"]}
            ],
            "citation_ids": [] if citations is None else citations,
        },
    }


def test_grounded_citation_mapping_is_server_owned_without_source_text():
    source = evidence()
    asset = uuid4()
    result = validate_card(card([1]), "materials", [source], {str(source.file_id): str(asset)})
    ref = result.citations[0].model_dump(mode="json")
    assert ref["file_id"] == str(source.file_id)
    assert ref["file_asset_id"] == str(asset)
    assert ref["processing_version_id"] == str(source.processing_version_id)
    assert ref["chunk_id"] == str(source.chunk_id)
    assert "content" not in ref
    assert result.source_mode == "materials"


@pytest.mark.parametrize("ids", [[0], [2], [1, 1], [True], ["1"], [1.0], []])
def test_invalid_material_citations_fail_closed(ids):
    source = evidence()
    with pytest.raises(UpstreamServiceError) as error:
        validate_card(card(ids), "materials", [source], {str(source.file_id): str(uuid4())})
    assert error.value.error_key == "KNOWLEDGE_OUTPUT_INVALID"


def test_general_mode_cannot_claim_material_citations():
    with pytest.raises(UpstreamServiceError):
        validate_card(card([1]), "general", [evidence()], {})
    assert validate_card(card(), "general", [], {}).citations == []


@pytest.mark.parametrize(
    "field", ["concept", "applications", "principles", "examples", "misconceptions", "exercises"]
)
def test_all_five_sections_must_be_complete(field):
    raw = card()
    raw["card"][field] = " " if field == "concept" else []
    with pytest.raises(UpstreamServiceError):
        validate_card(raw, "general", [], {})


@pytest.mark.parametrize(
    "mutation",
    [
        lambda raw: raw["card"].update(citations=[]),
        lambda raw: raw["card"].update(source_mode="materials"),
        lambda raw: raw["card"]["examples"][0].update(title=" "),
        lambda raw: raw["card"]["exercises"][0].update(self_check_points=[" "]),
        lambda raw: raw["card"].update(concept="甲" * 6001),
        lambda raw: raw["card"].update(applications=["甲" * 6000] * 7),
        lambda raw: raw["card"].update(principles=["要点"] * 21),
    ],
)
def test_extra_metadata_blanks_and_budget_cannot_bypass_local_gate(mutation):
    raw = card()
    mutation(raw)
    with pytest.raises(UpstreamServiceError):
        validate_card(raw, "general", [], {})


def test_structured_refusal_cannot_publish_partial_or_general_content():
    raw = {"status": "evidence_insufficient", "reason": "没有主题依据", "card": None}
    with pytest.raises(ValidationAppError) as error:
        validate_card(raw, "materials", [], {})
    assert error.value.error_key == "KNOWLEDGE_EVIDENCE_INSUFFICIENT"
    for changed in [dict(raw, card=card()["card"]), raw]:
        with pytest.raises(UpstreamServiceError):
            validate_card(changed, "general", [], {})


def test_provider_schema_and_manifest_have_only_model_owned_fields():
    schema = generation_schema()
    content = schema["$defs"]["KnowledgeContent"]
    assert content["required"] == list(content["properties"])
    assert "SourceRef" not in schema["$defs"]
    assert "source_mode" not in content["properties"]
    assert "citations" not in content["properties"]
    assert "citation_ids" in content["properties"]
    manifest = prompt_manifest("generate")
    assert manifest == prompt_manifest("generate")
    assert manifest["scene_key"] == "knowledge_generate"
    assert all(len(part["sha256"]) == 64 for part in manifest["parts"])
    copied = deepcopy(manifest)
    copied["parts"][0]["sha256"] = "changed"
    assert prompt_manifest("generate") == manifest


def audit_fixture():
    source = evidence()
    validated = validate_card(card([1]), "materials", [source], {str(source.file_id): str(uuid4())})
    passages = audit_passages(validated)
    reviewed = {
        name: {
            "status": "supported",
            "reason": "合成测试对应引用支持",
            "evidence": [{"evidence_id": 1, "quote": source.content}],
        }
        for name in passages
    }
    return passages, [source], reviewed


def test_audit_covers_every_text_field_and_requires_exact_quotes():
    passages, evidence_list, reviewed = audit_fixture()
    assert "exercise_1_point_1" in passages and "example_1_title" in passages
    validate_audit(reviewed, passages, evidence_list)
    schema = audit_schema(
        {"passages": passages, "evidence": [{"number": 1, "content": "合成资料"}]}
    )
    assert set(schema["required"]) == set(passages)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.pop("concept"),
        lambda r: r.update(unexpected={}),
        lambda r: r["concept"].update(status="unsupported", reason="没有支持"),
        lambda r: r["concept"].update(reason=" "),
        lambda r: r["concept"].update(evidence=[]),
        lambda r: r["concept"].update(status=True),
        lambda r: r["concept"]["evidence"][0].update(quote="自造引文"),
        lambda r: r["concept"]["evidence"][0].update(evidence_id=2),
        lambda r: r["concept"]["evidence"][0].update(evidence_id=True),
    ],
)
def test_audit_missing_unsupported_malformed_and_forged_quotes_fail_closed(mutation):
    passages, evidence_list, reviewed = audit_fixture()
    mutation(reviewed)
    with pytest.raises(UpstreamServiceError) as error:
        validate_audit(reviewed, passages, evidence_list)
    assert error.value.error_key == "KNOWLEDGE_OUTPUT_INVALID"
