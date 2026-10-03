"""Provider protocol gates and opt-in synthetic-only model evaluation (no business DB)."""

import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from pydantic import SecretStr
from test_learning_knowledge_generation import card
from test_practice_generation import evidence

from xuemian_ai.core.config import get_settings
from xuemian_ai.core.errors import UpstreamServiceError, ValidationAppError
from xuemian_ai.learning_assets.generation import (
    QwenKnowledgeProvider,
    audit_passages,
    validate_audit,
    validate_card,
)


def settings():
    return SimpleNamespace(
        dashscope_api_key=SecretStr("synthetic-test-key"),
        learning_answer_model="qwen3.8-flash",
        ai_base_url="https://example.invalid/v1",
        learning_model_timeout_seconds=1,
    )


async def test_provider_sends_strict_schema_disables_external_tracing_and_sanitizes_failure():
    with (
        patch("xuemian_ai.learning_assets.generation.ChatOpenAI") as model,
        patch("xuemian_ai.learning_assets.generation.tracing_context") as tracing,
    ):
        model.return_value.ainvoke = AsyncMock(
            return_value=AIMessage(
                content=json.dumps(card()),
                response_metadata={"finish_reason": "stop"},
            )
        )
        provider = QwenKnowledgeProvider(settings())
        result = await provider.invoke("generate", {"config": {"topic": "事务"}})
        assert result["status"] == "ready"
        kwargs = model.return_value.ainvoke.call_args.kwargs
        assert kwargs["response_format"]["type"] == "json_schema"
        assert kwargs["response_format"]["json_schema"]["strict"] is True
        assert model.call_args.kwargs["extra_body"]["enable_thinking"] is False
        tracing.assert_called_once_with(enabled=False)
        model.return_value.ainvoke.side_effect = RuntimeError("synthetic private request body")
        with pytest.raises(UpstreamServiceError) as error:
            await provider.invoke("generate", {})
        assert error.value.error_key == "KNOWLEDGE_PROVIDER_UNAVAILABLE"
        assert "private" not in str(error.value)


@pytest.mark.parametrize(
    "content,finish",
    [
        (json.dumps(card()), "length"),
        ("[]", "stop"),
        ("not JSON", "stop"),
        (" " * 250_001, "stop"),
    ],
)
async def test_truncated_malformed_and_oversized_provider_outputs_are_not_published(
    content, finish
):
    with patch("xuemian_ai.learning_assets.generation.ChatOpenAI") as model:
        model.return_value.ainvoke = AsyncMock(
            return_value=AIMessage(
                content=content,
                response_metadata={"finish_reason": finish},
            )
        )
        with pytest.raises(UpstreamServiceError) as error:
            await QwenKnowledgeProvider(settings()).invoke("generate", {})
        assert error.value.error_key == "KNOWLEDGE_OUTPUT_INVALID"


@pytest.mark.skipif(
    not os.getenv("LEARNING_REAL_MODELS"),
    reason="explicit synthetic-only real model smoke required",
)
async def test_real_knowledge_provider_general_card():
    provider = QwenKnowledgeProvider(get_settings())
    raw = await provider.invoke(
        "generate",
        {
            "config": {
                "topic": "数据库事务的原子性",
                "source_mode": "general",
                "foundation": "know_concept",
                "depth": "systematic",
            },
            "effective_context": {"values": {"preferred_language": "zh-CN"}},
            "evidence": [],
        },
    )
    validated = validate_card(raw, "general", [], {})
    assert not validated.citations
    assert "事务" in validated.concept
    assert any(
        "回滚" in text or "撤销" in text for text in [validated.concept, *validated.principles]
    )


@pytest.mark.skipif(
    not os.getenv("LEARNING_REAL_MODELS"),
    reason="explicit synthetic-only real model smoke required",
)
async def test_real_knowledge_provider_grounded_synthetic_semantics():
    source = evidence()
    source.content = (
        "合成蓝杉队列V7仅用于测试。它采用双步提交：记录入待定区，然后确认落盘。"
        "确认前可通过撤销删除待定记录；确认后记录不可撤销，也不允许重复确认。"
        "提交令牌单次使用，重复使用会返回令牌已消费。它不支持事务回滚或数据压缩。"
        "适用场景是防止重复投递：消费者先写待定，再确认；未确认时可撤销。"
        "误区是把待定视为确认成功，或把已确认记录当成仍能撤销。"
        "例子：甲记录进入待定区后撤销，最终没有已确认记录。"
    )
    raw = await QwenKnowledgeProvider(get_settings()).invoke(
        "generate",
        {
            "config": {
                "topic": "合成蓝杉队列V7双步提交",
                "source_mode": "materials",
                "foundation": "unfamiliar",
                "depth": "quick",
            },
            "effective_context": {"values": {"preferred_language": "zh-CN"}},
            "evidence": [{"number": 1, "content": source.content}],
        },
    )
    validated = validate_card(raw, "materials", [source], {str(source.file_id): str(uuid4())})
    assert validated.citations[0].chunk_id == source.chunk_id
    explanation = "\n".join([validated.concept, *validated.principles, *validated.misconceptions])
    assert "待定" in explanation and "确认" in explanation
    assert "不可撤销" in explanation or "不能撤销" in explanation or "无法撤销" in explanation


@pytest.mark.skipif(
    not os.getenv("LEARNING_REAL_MODELS"),
    reason="explicit synthetic-only real model smoke required",
)
async def test_real_knowledge_provider_refuses_unrelated_synthetic_materials():
    source = evidence()
    source.content = "合成资料：蓝杉队列V7只支持双步提交。本段没有任何天文学信息。"
    raw = await QwenKnowledgeProvider(get_settings()).invoke(
        "generate",
        {
            "config": {
                "topic": "木星大红斑的形成机制",
                "source_mode": "materials",
                "foundation": "know_concept",
                "depth": "deep",
            },
            "effective_context": {"values": {"preferred_language": "zh-CN"}},
            "evidence": [{"number": 1, "content": source.content}],
        },
    )
    with pytest.raises(ValidationAppError) as error:
        validate_card(raw, "materials", [source], {str(source.file_id): str(uuid4())})
    assert error.value.error_key == "KNOWLEDGE_EVIDENCE_INSUFFICIENT"


@pytest.mark.skipif(
    not os.getenv("LEARNING_REAL_MODELS"),
    reason="explicit synthetic-only real model smoke required",
)
async def test_real_grounding_audit_rejects_unsupported_state_guarantee():
    source = evidence()
    source.content = (
        "Synthetic CedarQueue V7 supports two-step commit only. Step one writes a pending record; "
        "step two confirms it. Before confirmation cancellation is allowed, afterward it is not. "
        "A token can be used only once; reuse returns token consumed. "
        "Use it to prevent duplicate delivery. "
        "Example: cancel pending A before confirmation, so A is never committed. "
        "Common mistake: assuming pending records are already committed."
    )
    raw = {
        "status": "ready",
        "reason": "",
        "card": {
            "concept": "Synthetic CedarQueue V7 supports two-step commit only.",
            "applications": ["Prevent duplicate delivery."],
            "principles": ["A token can be used only once; reuse returns token consumed."],
            "examples": [
                {
                    "title": "Cancel pending A",
                    "content": "Cancel pending A before confirmation, so A is never committed.",
                }
            ],
            "misconceptions": ["Assuming pending records are already committed."],
            "exercises": [
                {
                    "question": "What happens on token reuse?",
                    "self_check_points": [
                        "Reuse returns token consumed and guarantees every record "
                        "remains unchanged "
                        "and no new records are created."
                    ],
                }
            ],
            "citation_ids": [1],
        },
    }
    candidate = validate_card(raw, "materials", [source], {str(source.file_id): str(uuid4())})
    passages = audit_passages(candidate)
    review = await QwenKnowledgeProvider(get_settings()).invoke(
        "audit",
        {
            "passages": passages,
            "evidence": [{"number": 1, "content": source.content}],
        },
    )
    assert review["exercise_1_point_1"]["status"] == "unsupported"
    with pytest.raises(UpstreamServiceError) as error:
        validate_audit(review, passages, [source])
    assert error.value.error_key == "KNOWLEDGE_OUTPUT_INVALID"


async def test_audit_provider_maps_only_allowed_span_ids_to_exact_source_quotes():
    payload = {
        "passages": {"concept": "事务是操作集合"},
        "evidence": [{"number": 1, "content": "事务是操作集合。\n这是合成资料。"}],
    }
    reviewed = {
        "concept": {
            "status": "supported",
            "reason": "给定句子明确支持",
            "evidence": [{"span_id": 0}],
        }
    }
    with patch("xuemian_ai.learning_assets.generation.ChatOpenAI") as model:
        model.return_value.ainvoke = AsyncMock(
            return_value=AIMessage(
                content=json.dumps(reviewed),
                response_metadata={"finish_reason": "stop"},
            )
        )
        result = await QwenKnowledgeProvider(settings()).invoke("audit", payload)
        assert result["concept"]["evidence"] == [{"evidence_id": 1, "quote": "事务是操作集合。"}]
        schema = model.return_value.ainvoke.call_args.kwargs["response_format"]["json_schema"][
            "schema"
        ]
        assert schema["$defs"]["AuditEvidence"]["properties"]["span_id"]["enum"] == [0, 1]
        reviewed["concept"]["evidence"] = [{"span_id": True}]
        model.return_value.ainvoke.return_value = AIMessage(
            content=json.dumps(reviewed), response_metadata={"finish_reason": "stop"}
        )
        with pytest.raises(UpstreamServiceError) as failure:
            await QwenKnowledgeProvider(settings()).invoke("audit", payload)
        assert failure.value.error_key == "KNOWLEDGE_OUTPUT_INVALID"
        reviewed["concept"]["evidence"] = [{"span_id": 0}]
        model.return_value.ainvoke.return_value = AIMessage(
            content=json.dumps(reviewed), response_metadata={"finish_reason": "length"}
        )
        with pytest.raises(UpstreamServiceError):
            await QwenKnowledgeProvider(settings()).invoke("audit", payload)
