"""Real PostgreSQL tests restricted to an explicitly selected disposable database."""

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text
from test_practice_domain_integration import material_fixture, prepared

from xuemian_ai.accounts.models import User
from xuemian_ai.core.config import get_settings
from xuemian_ai.core.errors import ConflictError, NotFoundError, ValidationAppError
from xuemian_ai.infrastructure.database import create_database_engine, create_session_factory
from xuemian_ai.learning_assets.models import KnowledgeRun, LearningEvidenceEvent
from xuemian_ai.learning_assets.projection import LearningProjection, append_evidence_event
from xuemian_ai.learning_assets.schemas import (
    ExplanationCreate,
    ExplanationRegenerate,
    MasteryRequest,
    WeaknessCreate,
    WeaknessPatch,
)
from xuemian_ai.learning_assets.service import LearningAssetService, list_active_weaknesses
from xuemian_ai.learning_assets.targets import WeaknessTarget
from xuemian_ai.practice.models import PracticeGrade, PracticeSet
from xuemian_ai.practice.schemas import (
    AnswerSave,
    AttemptCreate,
    GradePayload,
    PracticeConfig,
    SetCreate,
    SingleAnswer,
    SubmitRequest,
)
from xuemian_ai.practice.service import PracticeService

pytestmark = pytest.mark.skipif(
    not os.getenv("LEARNING_ASSETS_INTEGRATION_DB"), reason="explicit isolated database required"
)


@pytest_asyncio.fixture
async def assets():
    settings = get_settings()
    assert settings.environment == "test"
    engine = create_database_engine(settings.database_url.get_secret_value())
    sessions = create_session_factory(engine)
    async with engine.connect() as connection:
        assert (
            await connection.scalar(text("SELECT current_database()"))
            == os.environ["LEARNING_ASSETS_INTEGRATION_DB"]
        )
    async with sessions.begin() as session:
        user = User(
            username="assets" + uuid4().hex[:16],
            nickname="Synthetic learner",
            password_hash="not-login",
            status="active",
            role="user",
        )
        session.add(user)
        await session.flush()
    domain = LearningAssetService(sessions, user.id, settings)
    try:
        yield domain, PracticeService(sessions, user.id, settings)
    finally:
        async with sessions.begin() as session:
            await session.execute(delete(User).where(User.id == user.id))
        await engine.dispose()


def payload():
    return {
        "concept": "事务原子性",
        "applications": ["转账"],
        "principles": ["全部提交或回滚"],
        "examples": [{"title": "转账", "content": "借贷同一事务"}],
        "misconceptions": ["仅隔离不保证原子"],
        "exercises": [{"question": "回滚时什么变化？", "self_check_points": ["未提交写入撤销"]}],
        "citations": [],
        "source_mode": "general",
    }


async def drain(domain):
    projection = LearningProjection(domain.sessions, domain.settings)
    for _ in range(100):
        if not await projection.process_next():
            return
    raise AssertionError("projection did not drain")


async def submit(practice, attempt_id, question_id, correct=False):
    current = await practice.get_attempt(attempt_id)
    saved = await practice.save_answer(
        attempt_id,
        question_id,
        AnswerSave(
            expected_version=current.version,
            answer=SingleAnswer(type="single_choice", option_id="A" if correct else "B"),
        ),
    )
    answer = next(answer for answer in saved.answers if answer.question_id == question_id)
    return await practice.submit(
        attempt_id,
        question_id,
        SubmitRequest(
            expected_version=saved.version, answer_version=answer.version, request_key=uuid4()
        ),
    )


async def test_manual_evidence_private_idempotency_versions_and_card_failure(assets):
    domain, _ = assets
    request = WeaknessCreate(title="事务", tags=["数据库"], request_key=uuid4())
    obj = await domain.create(request)
    assert (await domain.create(request)).id == obj.id
    detail = await domain.detail(obj.id)
    assert detail.evidence[0].kind == "manual" and detail.evidence[0].grade_id is None
    assert detail.evidence[0].detail["declaration"] == "user_learning_goal"
    assert detail.run.status == "pending"
    assert detail.evidence_count == detail.available_evidence_count == 1
    async with domain.sessions() as session:
        assert (await list_active_weaknesses(session, domain.owner))[
            0
        ].source_summary == "用户主动学习目标"
    with pytest.raises(ConflictError):
        await domain.create(request.model_copy(update={"title": "其他概念"}))
    outsider = LearningAssetService(domain.sessions, uuid4(), domain.settings)
    for read in [
        outsider.detail(obj.id),
        outsider.explanation_detail(obj.explanation_id),
        outsider.get_run(detail.run.id),
    ]:
        with pytest.raises(NotFoundError):
            await read
    claim = await domain.claim_run("test")
    assert await domain.publish_run(claim.id, claim.lease_token, payload())
    explanation = await domain.explanation_detail(obj.explanation_id)
    assert explanation.active_card_version == 1 and explanation.card_versions == [1]
    again = await domain.regenerate(
        explanation.id,
        ExplanationRegenerate(expected_version=explanation.version, request_key=uuid4()),
    )
    newclaim = await domain.claim_run("test")
    await domain.fail_run(newclaim.id, newclaim.lease_token, "KNOWLEDGE_PROVIDER_UNAVAILABLE", True)
    latest = await domain.explanation_detail(explanation.id)
    assert latest.active_card_version == 1 and latest.run.status == "failed"
    assert (await domain.get_card(explanation.id, 1)).concept == payload()["concept"]
    await domain.retry(again.run.id, again.run.request_key, again.run.input_digest)
    retryclaim = await domain.claim_run("test")
    assert retryclaim.attempt_count == 2
    await domain.cancel(retryclaim.id)
    assert not await domain.publish_run(retryclaim.id, retryclaim.lease_token, payload())
    changed = await domain.patch(
        obj.id, WeaknessPatch(expected_version=obj.version, title="事务知识")
    )
    assert changed.version == obj.version + 1
    refreshed = await domain.explanation_detail(explanation.id)
    renamed_run = await domain.regenerate(
        explanation.id,
        ExplanationRegenerate(expected_version=refreshed.version, request_key=uuid4()),
    )
    rename_claim = await domain.claim_run("rename-test")
    assert rename_claim.input_snapshot["config"]["topic"] == changed.title
    assert await domain.publish_run(rename_claim.id, rename_claim.lease_token, payload())
    assert (await domain.get_card(explanation.id, 1)).config.topic == "事务"
    assert (await domain.get_card(explanation.id, 2)).config.topic == changed.title
    assert renamed_run.run.explanation_id == explanation.id
    with pytest.raises(ConflictError):
        await domain.mastery(
            obj.id, MasteryRequest(expected_version=obj.version, mastery_state="mastered")
        )


async def test_outbox_replay_distinct_questions_and_recent_correct_regrade(assets):
    domain, practice = assets
    obj, revision = await prepared(practice, 3)
    attempt = await practice.create_attempt(
        obj.id,
        AttemptCreate(expected_version=obj.version, revision_id=revision.id, request_key=uuid4()),
    )
    for question in revision.questions[:2]:
        await submit(practice, attempt.id, question.question_id)
    second = await practice.create_attempt(
        obj.id,
        AttemptCreate(expected_version=obj.version, revision_id=revision.id, request_key=uuid4()),
    )
    await submit(practice, second.id, revision.questions[2].question_id)
    await drain(domain)
    items = await domain.list_weaknesses()
    assert len(items.data) == 1 and items.data[0].decision == "confirmed"
    weakness = await domain.detail(items.data[0].id)
    assert len([item for item in weakness.evidence if not item.superseded]) == 3
    async with domain.sessions() as session:
        count = len(
            list(
                await session.scalars(
                    select(KnowledgeRun).where(KnowledgeRun.owner_user_id == domain.owner)
                )
            )
        )
        first_grade = await session.scalar(
            select(PracticeGrade).where(PracticeGrade.owner_user_id == domain.owner)
        )
    async with domain.sessions.begin() as session:
        await append_evidence_event(
            session, domain.owner, "grade_published", first_grade.id, first_grade.version
        )
    await drain(domain)
    async with domain.sessions() as session:
        assert (
            len(
                list(
                    await session.scalars(
                        select(KnowledgeRun).where(KnowledgeRun.owner_user_id == domain.owner)
                    )
                )
            )
            == count
            == 1
        )
    # Regrade correction preserves old grade/evidence history and the confirmed asset.
    async with domain.sessions.begin() as session:
        submission = await practice._submission(session, first_grade.submission_id)
        await practice._save_grade(
            session,
            submission,
            GradePayload(
                level="correct",
                dimensions=[{"dimension_id": "correct", "level": "correct"}],
                confidence=1,
            ),
        )
    await drain(domain)
    corrected = await domain.detail(weakness.id)
    assert corrected.decision == "confirmed" and not corrected.evidence_sufficient
    assert any(item.superseded for item in corrected.evidence)
    assert any(item.event_type == "evidence_corrected" for item in corrected.events)


async def test_ignored_candidate_replay_and_soft_deleted_source_redaction(assets):
    domain, practice = assets
    obj, revision = await prepared(practice, 2)
    attempt = await practice.create_attempt(
        obj.id,
        AttemptCreate(expected_version=obj.version, revision_id=revision.id, request_key=uuid4()),
    )
    await submit(practice, attempt.id, revision.questions[0].question_id)
    await drain(domain)
    candidate = (await domain.list_weaknesses(decision="pending")).data[0]
    ignored = await domain.decide(candidate.id, candidate.version, "ignored")
    await submit(practice, attempt.id, revision.questions[0].question_id)
    await drain(domain)
    assert not (await domain.list_weaknesses(decision="pending")).data
    await submit(practice, attempt.id, revision.questions[1].question_id)
    await drain(domain)
    reopened = (await domain.list_weaknesses(decision="pending")).data[0]
    assert reopened.id == ignored.id
    assert (await domain.detail(reopened.id)).available_evidence_count == 1
    await practice.delete(obj.id, obj.version)
    await drain(domain)
    detail = await domain.detail(reopened.id)
    assert all(not item.available and item.detail is None for item in detail.evidence)
    with pytest.raises(ConflictError):
        await domain.decide(reopened.id, detail.version, "confirmed", uuid4())


async def test_targeted_review_denominator_completion_and_user_fence(assets):
    domain, practice = assets
    weakness = await domain.create(WeaknessCreate(title="事务", request_key=uuid4()))
    config = PracticeConfig(
        topic="事务",
        question_count=3,
        question_types={"single_choice": 3},
        learning_target=WeaknessTarget(kind="weakness", id=weakness.id, version=weakness.version),
    )
    with pytest.raises(ValidationAppError) as error:
        await practice.create(
            SetCreate(config=config.model_copy(update={"topic": "其他主题"}), request_key=uuid4())
        )
    assert error.value.error_key == "LEARNING_TARGET_MISMATCH"
    created = await practice.create(SetCreate(config=config, request_key=uuid4()))
    # Seed valid frozen questions as generation seam, using real target context from create.
    _, reference = await prepared(practice, 3)
    from xuemian_ai.practice.models import PracticeRevision

    async with domain.sessions.begin() as session:
        obj = await session.get(PracticeSet, created.id)
        revision = PracticeRevision(
            owner_user_id=domain.owner,
            set_id=obj.id,
            version=1,
            config=obj.config,
            effective_context=obj.effective_context,
            source_snapshot=[],
            questions=[question.model_dump(mode="json") for question in reference.questions],
            reason="test_generation",
        )
        session.add(revision)
        await session.flush()
        obj.current_revision_id = revision.id
        revision_id = revision.id
    attempt = await practice.create_attempt(
        created.id,
        AttemptCreate(
            expected_version=created.version, revision_id=revision_id, request_key=uuid4()
        ),
    )
    # A target edit after attempt start cannot break immutable existing answers/scoring.
    updated = await domain.mastery(
        weakness.id, MasteryRequest(expected_version=weakness.version, mastery_state="to_verify")
    )
    for question in reference.questions[:2]:
        await submit(practice, attempt.id, question.question_id, True)
    await drain(domain)
    current = await practice.get_attempt(attempt.id)
    await practice.complete(attempt.id, current.version)
    await drain(domain)
    review = (await domain.reviews(weakness.id, 1, 20)).data[0]
    assert (
        review.total_related == 3 and review.submitted_count == 2 and not review.validation_passed
    )
    assert review.conclusion == "incomplete_evidence"
    report = await practice.report(attempt.id)
    assert (
        report.learning_target
        and report.learning_review
        and report.learning_review.total_related == 3
    )
    assert (await domain.detail(weakness.id)).mastery_state == updated.mastery_state


async def test_lease_expiry_deleted_explanation_and_direct_explanation_no_weakness(assets):
    domain, _ = assets
    result = await domain.create_explanation(ExplanationCreate(topic="索引", request_key=uuid4()))
    assert (await domain.list_weaknesses()).meta.total == 0
    claim = await domain.claim_run("test")
    async with domain.sessions.begin() as session:
        row = await session.get(KnowledgeRun, claim.id)
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert await domain.recover_expired() == 1
    assert not await domain.heartbeat(claim.id, claim.lease_token)
    assert not await domain.publish_run(claim.id, claim.lease_token, payload())
    await domain.retry(claim.id, claim.request_key, claim.input_digest)
    resumed = await domain.claim_run("test")
    await domain.delete_explanation(result.explanation.id, result.explanation.version)
    assert not await domain.publish_run(resumed.id, resumed.lease_token, payload())
    assert (await domain.get_run(claim.id)).status == "cancelled"


async def test_no_historical_backfill_manual_stays_sufficient_and_rename_stays_one_asset(assets):
    domain, practice = assets
    manual = await domain.create(WeaknessCreate(title="索引", request_key=uuid4()))
    obj, revision = await prepared(practice, 1)
    attempt = await practice.create_attempt(
        obj.id,
        AttemptCreate(expected_version=obj.version, revision_id=revision.id, request_key=uuid4()),
    )
    await submit(practice, attempt.id, revision.questions[0].question_id)
    async with domain.sessions.begin() as session:
        await session.execute(
            delete(LearningEvidenceEvent).where(LearningEvidenceEvent.owner_user_id == domain.owner)
        )
    current = await practice.get_attempt(attempt.id)
    await practice.complete(attempt.id, current.version)
    await drain(domain)
    assert not (await domain.list_weaknesses(decision="pending")).data
    assert (await domain.detail(manual.id)).evidence_sufficient
    # Only a genuinely new published score starts a candidate, not the old completed attempt.
    new = await practice.create_attempt(
        obj.id,
        AttemptCreate(expected_version=obj.version, revision_id=revision.id, request_key=uuid4()),
    )
    await submit(practice, new.id, revision.questions[0].question_id)
    await drain(domain)
    candidate = (await domain.list_weaknesses(decision="pending")).data[0]
    renamed = await domain.patch(
        candidate.id, WeaknessPatch(expected_version=candidate.version, title="事务原子性")
    )
    new_current = await practice.get_attempt(new.id)
    await practice.complete(new.id, new_current.version)
    await drain(domain)
    all_candidates = (await domain.list_weaknesses(decision="pending")).data
    assert (
        len(all_candidates) == 1
        and all_candidates[0].id == renamed.id
        and all_candidates[0].title == "事务原子性"
    )


async def test_disabled_account_stops_claim_heartbeat_and_publish(assets):
    domain, _ = assets
    result = await domain.create_explanation(ExplanationCreate(topic="索引", request_key=uuid4()))
    claim = await domain.claim_run("test")
    async with domain.sessions.begin() as session:
        user = await session.get(User, domain.owner)
        user.status = "disabled"
    with pytest.raises(NotFoundError):
        await domain.heartbeat(claim.id, claim.lease_token)
    with pytest.raises(NotFoundError):
        await domain.publish_run(claim.id, claim.lease_token, payload())
    assert (await domain.explanation_detail(result.explanation.id)).card is None
    await domain.fail_run(claim.id, claim.lease_token, "LEARNING_ASSET_NOT_FOUND", False)
    async with domain.sessions.begin() as session:
        user = await session.get(User, domain.owner)
        user.status = "active"
    waiting = await domain.create_explanation(ExplanationCreate(topic="锁", request_key=uuid4()))
    async with domain.sessions.begin() as session:
        user = await session.get(User, domain.owner)
        user.status = "disabled"
    assert await domain.claim_run("test") is None
    assert (await domain.get_run(waiting.run.id)).status == "failed"


async def test_latest_ungraded_submission_supersedes_old_evidence_before_grade_success(assets):
    domain, practice = assets
    obj, revision = await prepared(practice, 1)
    first = await practice.create_attempt(
        obj.id,
        AttemptCreate(expected_version=obj.version, revision_id=revision.id, request_key=uuid4()),
    )
    await submit(practice, first.id, revision.questions[0].question_id)
    await drain(domain)
    candidate = (await domain.list_weaknesses(decision="pending")).data[0]
    from xuemian_ai.practice.schemas import ShortAnswerQuestion, TextAnswer

    original = revision.questions[0]
    replacement = ShortAnswerQuestion(
        question_id=original.question_id,
        type="short_answer",
        topics=original.topics,
        stem=original.stem,
        answer_explanation=original.answer_explanation,
        rubric=original.rubric,
        answer=["原子性"],
    )
    edited = await practice.edit_question(obj.id, original.question_id, obj.version, replacement)
    current_set = await practice.detail(obj.id)
    second = await practice.create_attempt(
        obj.id,
        AttemptCreate(
            expected_version=current_set.version, revision_id=edited.id, request_key=uuid4()
        ),
    )
    saved = await practice.save_answer(
        second.id,
        original.question_id,
        AnswerSave(
            expected_version=second.version,
            answer=TextAnswer(type="short_answer", text="尚未评分的新回答"),
        ),
    )
    queued = await practice.submit(
        second.id,
        original.question_id,
        SubmitRequest(
            expected_version=saved.version,
            answer_version=saved.answers[0].version,
            request_key=uuid4(),
        ),
    )
    assert queued.status == "pending"
    await drain(domain)
    detail = await domain.detail(candidate.id)
    assert all(item.superseded for item in detail.evidence)
    assert detail.available_evidence_count == 0
    assert not detail.evidence_sufficient


async def targeted_setup(domain, practice, count=3):
    weakness = await domain.create(WeaknessCreate(title="事务", request_key=uuid4()))
    config = PracticeConfig(
        topic="事务",
        question_count=count,
        question_types={"single_choice": count},
        learning_target=WeaknessTarget(kind="weakness", id=weakness.id, version=weakness.version),
    )
    created = await practice.create(SetCreate(config=config, request_key=uuid4()))
    _, reference = await prepared(practice, count)
    from xuemian_ai.practice.models import PracticeRevision

    async with domain.sessions.begin() as session:
        obj = await session.get(PracticeSet, created.id)
        revision = PracticeRevision(
            owner_user_id=domain.owner,
            set_id=obj.id,
            version=1,
            config=obj.config,
            effective_context=obj.effective_context,
            source_snapshot=[],
            questions=[question.model_dump(mode="json") for question in reference.questions],
            reason="test_generation",
        )
        session.add(revision)
        await session.flush()
        obj.current_revision_id = revision.id
        revision_id = revision.id
    attempt = await practice.create_attempt(
        created.id,
        AttemptCreate(
            expected_version=created.version, revision_id=revision_id, request_key=uuid4()
        ),
    )
    return weakness, created, reference.questions, attempt


async def test_complete_validation_regression_and_late_user_state_fence(assets):
    domain, practice = assets
    weakness, created, questions, attempt = await targeted_setup(domain, practice)
    for question in questions:
        await submit(practice, attempt.id, question.question_id, True)
    await drain(domain)
    before = (await domain.reviews(weakness.id, 1, 20)).data[0]
    assert not before.validation_passed and before.conclusion == "in_progress"
    current = await practice.get_attempt(attempt.id)
    await practice.complete(attempt.id, current.version)
    await drain(domain)
    after = (await domain.reviews(weakness.id, 1, 20)).data[0]
    assert after.validation_passed and after.version > before.version
    assert (await domain.detail(weakness.id)).mastery_state == "to_learn"
    marked = await domain.mastery(
        weakness.id, MasteryRequest(expected_version=weakness.version, mastery_state="mastered")
    )
    second = await practice.create_attempt(
        created.id,
        AttemptCreate(
            expected_version=created.version, revision_id=attempt.revision_id, request_key=uuid4()
        ),
    )
    await submit(practice, second.id, questions[0].question_id, False)
    await drain(domain)
    regressed = await domain.detail(weakness.id)
    assert regressed.mastery_state == "learning" and regressed.version > marked.version
    # A user action after the wrong answer fences even an outbox replay/regrade event.
    latest_mark = await domain.mastery(
        weakness.id, MasteryRequest(expected_version=regressed.version, mastery_state="mastered")
    )
    async with domain.sessions.begin() as session:
        await append_evidence_event(session, domain.owner, "attempt_completed", second.id, 99)
    await drain(domain)
    assert (await domain.detail(weakness.id)).mastery_state == latest_mark.mastery_state


async def test_material_review_source_round_trips_append_without_duplicate_history(assets):
    from xuemian_ai.document_processing.models import DocumentProcessingVersion

    domain, practice = assets
    material_set, reference, file_id, source_version_id = await material_fixture(practice)
    weakness = await domain.create(
        WeaknessCreate(
            title="事务",
            source_mode="materials",
            knowledge_base_id=material_set.config.knowledge_base_id,
            file_ids=[file_id],
            request_key=uuid4(),
        )
    )
    config = PracticeConfig(
        topic="事务",
        source_mode="materials",
        knowledge_base_id=material_set.config.knowledge_base_id,
        file_ids=[file_id],
        question_count=3,
        question_types={"single_choice": 3},
        learning_target=WeaknessTarget(kind="weakness", id=weakness.id, version=weakness.version),
    )
    created = await practice.create(SetCreate(config=config, request_key=uuid4()))
    questions = [
        {
            **reference.questions[0],
            "question_id": str(uuid4()),
            "stem": f"合成复习题 {index}：{reference.questions[0]['stem']}",
        }
        for index in range(3)
    ]
    async with domain.sessions.begin() as session:
        persisted = await practice._set(session, created.id, True)
        revision = await practice._new_revision(
            session,
            persisted,
            questions,
            persisted.config,
            persisted.effective_context,
            persisted.source_snapshot,
            "generate",
        )
    generated = await practice.detail(created.id)
    attempt = await practice.create_attempt(
        created.id,
        AttemptCreate(
            expected_version=generated.version, revision_id=revision.id, request_key=uuid4()
        ),
    )
    for question in questions:
        await submit(practice, attempt.id, UUID(question["question_id"]), True)
    current = await practice.get_attempt(attempt.id)
    await practice.complete(attempt.id, current.version)
    await drain(domain)
    assert (await domain.reviews(weakness.id, 1, 20)).data[0].validation_passed

    # 直接控制合成来源的活动状态，验证相同版本再次可用时真实唯一约束仍成立。
    for index, active in enumerate([False, True, False, True], start=1):
        async with domain.sessions.begin() as session:
            source = await session.get(DocumentProcessingVersion, source_version_id)
            source.status = "active" if active else "retired"
            await append_evidence_event(
                session, domain.owner, "attempt_completed", attempt.id, index + 100
            )
        await drain(domain)
        reviews = await domain.reviews(weakness.id, 1, 20)
        assert reviews.meta.total == index + 1
        assert reviews.data[0].version == index + 1
        assert reviews.data[0].validation_passed == active
        assert reviews.data[0].conclusion == (
            "validation_passed" if active else "source_unavailable"
        )
        async with domain.sessions.begin() as session:
            await append_evidence_event(
                session, domain.owner, "attempt_completed", attempt.id, index + 200
            )
        await drain(domain)
        assert (await domain.reviews(weakness.id, 1, 20)).meta.total == index + 1


async def test_projection_and_answer_submission_do_not_deadlock(assets):
    import asyncio

    domain, practice = assets
    weakness, _, questions, attempt = await targeted_setup(domain, practice)
    await domain.mastery(
        weakness.id, MasteryRequest(expected_version=weakness.version, mastery_state="to_verify")
    )
    for i in range(6):
        await asyncio.wait_for(
            asyncio.gather(
                submit(practice, attempt.id, questions[i % len(questions)].question_id, i % 2 == 0),
                drain(domain),
            ),
            timeout=10,
        )
    await drain(domain)
    report = await practice.report(attempt.id)
    assert report.submitted_count == 3
    detail = await domain.detail(weakness.id)
    assert detail.mastery_state == "learning" and detail.reviews


@pytest.mark.parametrize("revoke", ["delete", "move", "version"])
async def test_material_card_source_revocation_and_explicit_same_scope_refresh(assets, revoke):
    from xuemian_ai.document_processing.models import DocumentChunk, DocumentProcessingVersion
    from xuemian_ai.file_management.models import KnowledgeBaseFile
    from xuemian_ai.knowledge_bases.models import KnowledgeBase

    domain, practice = assets
    obj, revision, file_id, version_id = await material_fixture(practice)
    weakness = await domain.create(
        WeaknessCreate(
            title="事务",
            source_mode="materials",
            knowledge_base_id=obj.config.knowledge_base_id,
            file_ids=[file_id],
            request_key=uuid4(),
        )
    )
    claim = await domain.claim_run("materials-test")
    original_payload = {
        **payload(),
        "source_mode": "materials",
        "citations": revision.questions[0]["source_refs"],
    }
    assert await domain.publish_run(claim.id, claim.lease_token, original_payload)
    first = await domain.explanation_detail(weakness.explanation_id)
    assert first.card.source_available
    preview = await domain.source_preview(first.id, 1, "1")
    assert preview.available and preview.evidence == "Synthetic private original content"
    new_version_id = new_chunk_id = None
    async with domain.sessions.begin() as session:
        binding = await session.get(KnowledgeBaseFile, file_id)
        if revoke == "delete":
            binding.deleted_at = datetime.now(UTC)
        elif revoke == "move":
            kb = KnowledgeBase(owner_user_id=domain.owner, name="Moved synthetic", is_default=False)
            session.add(kb)
            await session.flush()
            binding.knowledge_base_id = kb.id
        else:
            previous = await session.get(DocumentProcessingVersion, version_id)
            previous.status = "retired"
            await session.flush()
            new_version = DocumentProcessingVersion(
                user_id=domain.owner,
                file_asset_id=previous.file_asset_id,
                task_id=previous.task_id,
                profile_id=previous.profile_id,
                version_number=2,
                status="active",
                parser_version="new-synthetic",
                chunk_strategy_version="new",
                ocr_strategy_version="new",
            )
            session.add(new_version)
            await session.flush()
            chunk = DocumentChunk(
                processing_version_id=new_version.id,
                file_asset_id=previous.file_asset_id,
                user_id=domain.owner,
                ordinal=0,
                content="New synthetic source evidence",
                content_digest=uuid4().hex * 2,
                source_kind="native",
                paragraph_start=1,
                paragraph_end=1,
                search_vector="",
            )
            session.add(chunk)
            await session.flush()
            new_version_id, new_chunk_id = new_version.id, chunk.id
    preserved = await domain.get_card(first.id, 1)
    assert not preserved.source_available and preserved.concept == first.card.concept
    withdrawn = await domain.source_preview(first.id, 1, "1")
    assert not withdrawn.available and withdrawn.evidence is None
    if revoke != "version":
        with pytest.raises(ConflictError):
            await domain.regenerate(
                first.id, ExplanationRegenerate(expected_version=first.version, request_key=uuid4())
            )
        assert (await domain.explanation_detail(first.id)).active_card_version == 1
        return
    # Explicit regeneration may refresh processing version, never the logical file scope.
    second = await domain.regenerate(
        first.id, ExplanationRegenerate(expected_version=first.version, request_key=uuid4())
    )
    changed = await domain.detail(weakness.id)
    assert changed.version > weakness.version
    assert any(item.event_type == "source_refreshed" for item in changed.events)
    assert changed.file_ids == [file_id]
    claim = await domain.claim_run("refresh-test")
    citation = {
        **original_payload["citations"][0],
        "processing_version_id": str(new_version_id),
        "chunk_id": str(new_chunk_id),
    }
    assert await domain.publish_run(
        claim.id, claim.lease_token, {**original_payload, "citations": [citation]}
    )
    final = await domain.explanation_detail(first.id)
    assert (
        final.card_versions == [2, 1]
        and final.active_card_version == 2
        and final.card.source_available
    )
    assert not (await domain.get_card(first.id, 1)).source_available
    target_config = PracticeConfig(
        source_mode="materials",
        knowledge_base_id=changed.knowledge_base_id,
        file_ids=changed.file_ids,
        topic="事务",
        question_count=1,
        question_types={"single_choice": 1},
        learning_target=WeaknessTarget(kind="weakness", id=changed.id, version=changed.version),
    )
    targeted = await practice.create(SetCreate(config=target_config, request_key=uuid4()))
    assert targeted.source_available
    assert second.run.explanation_id == first.id


async def test_owner_joint_foreign_key_rejects_cross_owner_evidence(assets):
    from sqlalchemy.exc import IntegrityError

    from xuemian_ai.learning_assets.models import WeaknessEvidence

    domain, _ = assets
    weakness = await domain.create(WeaknessCreate(title="事务", request_key=uuid4()))
    async with domain.sessions.begin() as session:
        outsider = User(
            username="foreign" + uuid4().hex[:16],
            nickname="Synthetic outsider",
            password_hash="not-login",
            status="active",
            role="user",
        )
        session.add(outsider)
        await session.flush()
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(
                    WeaknessEvidence(
                        owner_user_id=outsider.id,
                        weakness_id=weakness.id,
                        kind="manual",
                        source_key="cross-owner-test",
                        detail={"declaration": "synthetic"},
                    )
                )
                await session.flush()
        await session.execute(delete(User).where(User.id == outsider.id))


async def test_renamed_soft_deleted_asset_cannot_revive_from_old_grade_events(assets):
    domain, practice = assets
    obj, revision = await prepared(practice, 4)
    first = await practice.create_attempt(
        obj.id,
        AttemptCreate(expected_version=obj.version, revision_id=revision.id, request_key=uuid4()),
    )
    for question in revision.questions[:2]:
        await submit(practice, first.id, question.question_id)
    second = await practice.create_attempt(
        obj.id,
        AttemptCreate(expected_version=obj.version, revision_id=revision.id, request_key=uuid4()),
    )
    await submit(practice, second.id, revision.questions[2].question_id)
    await drain(domain)
    confirmed = (await domain.list_weaknesses()).data[0]
    renamed = await domain.patch(
        confirmed.id, WeaknessPatch(expected_version=confirmed.version, title="事务原子性")
    )
    await domain.delete(renamed.id, renamed.version)
    # A different durable event re-reads the old original-topic scores after deletion.
    current = await practice.get_attempt(second.id)
    await practice.complete(second.id, current.version)
    await drain(domain)
    assert (await domain.list_weaknesses()).meta.total == 0
    assert (await domain.list_weaknesses(decision="pending")).meta.total == 0
    async with domain.sessions() as session:
        runs = list(
            await session.scalars(
                select(KnowledgeRun).where(KnowledgeRun.owner_user_id == domain.owner)
            )
        )
        assert len(runs) == 1 and runs[0].status == "cancelled"
    # A new independent question may create only a new pending candidate; old scores stay blocked.
    await submit(practice, first.id, revision.questions[3].question_id)
    await drain(domain)
    fresh = (await domain.list_weaknesses(decision="pending")).data
    assert len(fresh) == 1 and fresh[0].id != confirmed.id and not fresh[0].explanation_id
    assert not fresh[0].evidence_sufficient
    async with domain.sessions() as session:
        assert (
            len(
                list(
                    await session.scalars(
                        select(KnowledgeRun).where(KnowledgeRun.owner_user_id == domain.owner)
                    )
                )
            )
            == 1
        )


async def test_renamed_target_topics_merge_evidence_once_across_event_replays(assets):
    from xuemian_ai.learning_assets.models import WeaknessEvidence
    from xuemian_ai.practice.models import PracticeRevision

    domain, practice = assets
    original, old_revision = await prepared(practice, 3)
    first = await practice.create_attempt(
        original.id,
        AttemptCreate(
            expected_version=original.version, revision_id=old_revision.id, request_key=uuid4()
        ),
    )
    for question in old_revision.questions[:2]:
        await submit(practice, first.id, question.question_id)
    second = await practice.create_attempt(
        original.id,
        AttemptCreate(
            expected_version=original.version, revision_id=old_revision.id, request_key=uuid4()
        ),
    )
    await submit(practice, second.id, old_revision.questions[2].question_id)
    await drain(domain)
    asset = (await domain.list_weaknesses()).data[0]
    renamed = await domain.patch(
        asset.id, WeaknessPatch(expected_version=asset.version, title="事务原子性")
    )
    config = PracticeConfig(
        topic=renamed.title,
        question_count=3,
        question_types={"single_choice": 3},
        learning_target=WeaknessTarget(kind="weakness", id=renamed.id, version=renamed.version),
    )
    created = await practice.create(SetCreate(config=config, request_key=uuid4()))
    _, new_reference = await prepared(practice, 3)
    questions = [
        {
            **item.model_dump(mode="json"),
            "topics": [renamed.title],
            "stem": f"{renamed.title}合成验证题 {i}",
        }
        for i, item in enumerate(new_reference.questions)
    ]
    async with domain.sessions.begin() as session:
        obj = await session.get(PracticeSet, created.id)
        revision = PracticeRevision(
            owner_user_id=domain.owner,
            set_id=obj.id,
            version=1,
            config=obj.config,
            effective_context=obj.effective_context,
            source_snapshot=[],
            questions=questions,
            reason="test_generation",
        )
        session.add(revision)
        await session.flush()
        obj.current_revision_id = revision.id
        revision_id = revision.id
    target_attempt = await practice.create_attempt(
        created.id,
        AttemptCreate(
            expected_version=created.version, revision_id=revision_id, request_key=uuid4()
        ),
    )
    for question in questions:
        await submit(practice, target_attempt.id, UUID(question["question_id"]), True)
    current = await practice.get_attempt(target_attempt.id)
    await practice.complete(target_attempt.id, current.version)
    await drain(domain)
    # Reproduce a stale superseded flag left by per-topic projection before this fix.
    async with domain.sessions.begin() as session:
        evidence = list(
            await session.scalars(
                select(WeaknessEvidence).where(WeaknessEvidence.weakness_id == renamed.id)
            )
        )
        assert len(evidence) == 6
        for item in evidence:
            item.superseded = True
        await append_evidence_event(session, domain.owner, "attempt_completed", second.id, 90)
    for version in range(91, 94):
        await drain(domain)
        actual = await domain.detail(renamed.id)
        assert actual.available_evidence_count == 6 and all(
            not item.superseded for item in actual.evidence
        )
        assert not actual.evidence_sufficient  # the most recent two answers are correct
        assert (await domain.reviews(renamed.id, 1, 20)).data[0].validation_passed
        assert (await domain.list_weaknesses()).meta.total == 1
        async with domain.sessions.begin() as session:
            await append_evidence_event(
                session, domain.owner, "attempt_completed", second.id, version
            )
    await drain(domain)
    async with domain.sessions() as session:
        assert (
            len(
                list(
                    await session.scalars(
                        select(KnowledgeRun).where(KnowledgeRun.owner_user_id == domain.owner)
                    )
                )
            )
            == 1
        )
