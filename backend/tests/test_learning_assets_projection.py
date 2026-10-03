"""Synthetic projection regressions without a database or real learner content."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from xuemian_ai.learning_assets.models import LearningReview
from xuemian_ai.learning_assets.policy import fingerprint
from xuemian_ai.learning_assets.projection import LearningProjection


class ReviewSession:
    def __init__(self):
        self.reviews = []

    async def scalars(self, query):
        return self.reviews

    def add(self, review):
        assert isinstance(review, LearningReview)
        # 模拟数据库的两个唯一约束，避免修复在单元测试通过、落库时却冲突。
        assert all(item.input_digest != review.input_digest for item in self.reviews)
        assert all(item.version != review.version for item in self.reviews)
        self.reviews.append(review)


@pytest.mark.parametrize("legacy_history", [False, True])
async def test_review_source_restoration_appends_current_conclusion_and_replay_is_idempotent(
    legacy_history,
):
    owner, attempt_id, revision_id, set_id = uuid4(), uuid4(), uuid4(), uuid4()
    questions = [
        {"question_id": str(uuid4()), "topics": ["事务"], "type": "single_choice"} for _ in range(3)
    ]
    latest, grades, refs = {}, {}, []
    for question in questions:
        submission = SimpleNamespace(id=uuid4(), created_at=datetime.now(UTC))
        latest[(attempt_id, UUID(question["question_id"]))] = (submission,)
        grades[submission.id] = SimpleNamespace(id=uuid4(), payload={"level": "correct"})
        refs.append(
            {
                "question": question["question_id"],
                "submission": str(submission.id),
                "grade": str(grades[submission.id].id),
            }
        )
    attempt = SimpleNamespace(id=attempt_id, status="completed")
    revision = SimpleNamespace(
        id=revision_id, questions=questions, config={"topic": "事务"}, source_snapshot=[]
    )
    practice_set = SimpleNamespace(id=set_id, deleted_at=None)
    target = {"kind": "explanation", "id": str(uuid4()), "topic": "事务"}
    session = ReviewSession()
    projection = LearningProjection(None)
    available = AsyncMock(return_value=True)

    async def project():
        await projection._review(
            session, owner, attempt, revision, practice_set, target, latest, grades
        )

    with patch("xuemian_ai.learning_assets.projection.sources_available", available):
        await project()
        await project()
        assert len(session.reviews) == 1
        assert session.reviews[-1].validation_passed

        available.return_value = False
        await project()
        await project()
        assert len(session.reviews) == 2
        assert session.reviews[-1].conclusion == "source_unavailable"

        if legacy_history:
            # 复现升级前已有的两版直接内容摘要；升级不得改写旧历史。
            session.reviews[-1].input_digest = fingerprint(
                {
                    "refs": refs,
                    "completed": "completed",
                    "source_available": False,
                }
            )
            await project()
            assert len(session.reviews) == 2
        old_digests = [review.input_digest for review in session.reviews]

        # 同一合法来源版本重新可用时，旧的成功历史不能阻止当前结论恢复。
        available.return_value = True
        await project()
        await project()
        assert len(session.reviews) == 3
        assert session.reviews[-1].version == 3
        assert session.reviews[-1].validation_passed
        assert session.reviews[1].conclusion == "source_unavailable"
        assert [review.input_digest for review in session.reviews[:2]] == old_digests

        for expected_version, source_available in enumerate([False, True, False, True], start=4):
            available.return_value = source_available
            await project()
            await project()
            assert len(session.reviews) == expected_version
            assert session.reviews[-1].version == expected_version
            assert session.reviews[-1].validation_passed == source_available
