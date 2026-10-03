from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from xuemian_ai.learning_assets.policy import (
    Observation,
    automatic_confirmation,
    concept_key,
    review_conclusion,
    scope_key,
)
from xuemian_ai.learning_assets.schemas import (
    ExplanationCreate,
    KnowledgeCardPayload,
    WeaknessCreate,
)


def observations():
    now = datetime.now(UTC)
    attempts = [uuid4(), uuid4()]
    return now, [
        Observation(
            question_id=uuid4(),
            attempt_id=attempts[i % 2],
            submitted_at=now - timedelta(minutes=3 - i),
            level="incorrect",
            difficulty="medium",
            single_topic=True,
            low_confidence=False,
        )
        for i in range(3)
    ]


def test_three_independent_wrong_questions_across_two_attempts():
    now, items = observations()
    assert automatic_confirmation(items, now)
    assert not automatic_confirmation(items[:2], now)
    assert not automatic_confirmation(
        [replace(item, attempt_id=items[0].attempt_id) for item in items], now
    )
    assert not automatic_confirmation(
        [replace(item, question_id=items[0].question_id) for item in items], now
    )


@pytest.mark.parametrize(
    "change",
    [
        {"difficulty": "easy"},
        {"low_confidence": True},
        {"single_topic": False},
        {"available": False},
        {"ignored": True},
        {"submitted_at": datetime(2020, 1, 1, tzinfo=UTC)},
    ],
)
def test_ineligible_evidence_does_not_autoconfirm(change):
    now, items = observations()
    assert not automatic_confirmation([replace(item, **change) for item in items], now)


def test_recent_correct_result_blocks_old_wrong_history():
    now, items = observations()
    assert not automatic_confirmation(
        items + [replace(items[0], question_id=uuid4(), submitted_at=now, level="correct")], now
    )
    assert not automatic_confirmation(
        items + [replace(items[-1], submitted_at=now, level="correct")], now
    )


def test_scope_normalizes_unicode_and_file_order_without_merging_selected_ranges():
    assert concept_key("  ＴＲＡＮＳＡＣＴＩＯＮ\n Locks ") == "transaction locks"
    base = {"source_mode": "materials", "knowledge_base_id": str(uuid4())}
    a, b = str(uuid4()), str(uuid4())
    assert scope_key({**base, "file_ids": [a, b]}) == scope_key({**base, "file_ids": [b, a, a]})
    assert scope_key({**base, "file_ids": [a]}) != scope_key({**base, "file_ids": [b]})
    assert scope_key(base) != scope_key({**base, "file_ids": [a, b]})


@pytest.mark.parametrize(
    "args,expected",
    [
        ((3, 3, 3, 3, 0, True, True), (True, "validation_passed")),
        ((2, 2, 2, 2, 0, True, True), (False, "insufficient_sample")),
        ((4, 3, 3, 3, 0, True, True), (False, "incomplete_evidence")),
        ((3, 3, 3, 3, 1, True, True), (False, "low_confidence")),
        ((3, 3, 3, 3, 0, False, True), (False, "in_progress")),
        ((3, 3, 3, 3, 0, True, False), (False, "source_unavailable")),
    ],
)
def test_review_preserves_full_related_denominator(args, expected):
    assert review_conclusion(*args) == expected


def test_schema_rejects_missing_scope_target_and_blank_titles():
    with pytest.raises(ValidationError):
        WeaknessCreate(title=" ", request_key=uuid4())
    with pytest.raises(ValidationError):
        WeaknessCreate(title="事务", source_mode="materials", request_key=uuid4())
    with pytest.raises(ValidationError):
        ExplanationCreate(weakness_id=uuid4(), request_key=uuid4())
    with pytest.raises(ValidationError):
        ExplanationCreate(topic="", request_key=uuid4())
    with pytest.raises(ValidationError):
        KnowledgeCardPayload(
            concept="事务",
            applications=[""],
            principles=["原子"],
            examples=[{"title": "例", "content": "内容"}],
            misconceptions=["误区"],
            exercises=[{"question": "问题", "self_check_points": ["答案"]}],
            source_mode="general",
        )
