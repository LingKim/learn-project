"""Run only against an explicitly selected, disposable, migrated PostgreSQL database."""

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from managed_prompt_fixture import publish_test_prompt
from sqlalchemy import delete, select, text

from xuemian_ai.accounts.models import User
from xuemian_ai.core.config import get_settings
from xuemian_ai.core.errors import ConflictError, NotFoundError, ValidationAppError
from xuemian_ai.infrastructure.database import create_database_engine, create_session_factory
from xuemian_ai.practice.models import PracticeRun
from xuemian_ai.practice.schemas import (
    AnswerSave,
    AttemptCreate,
    GenerateRequest,
    PlanRequest,
    PracticeConfig,
    RegenerateRequest,
    RetryRequest,
    SetCreate,
    SetPatch,
    SingleAnswer,
    SubmitRequest,
)
from xuemian_ai.practice.service import PracticeService

pytestmark = pytest.mark.skipif(
    not os.getenv("PRACTICE_INTEGRATION_DB"), reason="explicit isolated database required"
)


@pytest_asyncio.fixture
async def domain():
    settings = get_settings()
    assert settings.environment == "test"
    engine = create_database_engine(settings.database_url.get_secret_value())
    sessions = create_session_factory(engine)
    async with engine.connect() as connection:
        assert (
            await connection.scalar(text("SELECT current_database()"))
            == os.environ["PRACTICE_INTEGRATION_DB"]
        )
    async with sessions.begin() as session:
        user = User(
            username="practice" + uuid4().hex[:16],
            nickname="Synthetic learner",
            password_hash="not-a-login-hash",
            status="active",
            role="user",
        )
        session.add(user)
        await session.flush()
    await publish_test_prompt(sessions, settings)
    service = PracticeService(sessions, user.id, settings)
    try:
        yield service
    finally:
        async with sessions.begin() as session:
            await session.execute(delete(User).where(User.id == user.id))
        await engine.dispose()


def question(number=1):
    return {
        "question_id": str(uuid4()),
        "type": "single_choice",
        "difficulty": "medium",
        "topics": ["事务"],
        "stem": f"合成事务题 {number}",
        "answer_explanation": "正确选项为 A",
        "rubric": [{"id": "correct", "description": "选择 A 得分", "max_score": 1}],
        "options": [{"id": "A", "text": "原子性"}, {"id": "B", "text": "脏读"}],
        "answer": "A",
        "source_refs": [],
    }


async def prepared(domain, count=2):
    config = PracticeConfig(
        topic="事务", question_count=count, question_types={"single_choice": count}
    )
    obj = await domain.create(SetCreate(config=config, request_key=uuid4()))
    plan = await domain.plan(obj.id, PlanRequest(expected_version=obj.version, request_key=uuid4()))
    claim = await domain.claim_run("test")
    assert claim.id == plan.id
    await domain.publish_run(
        claim.id,
        claim.lease_token,
        {
            "recommended_config": config.model_dump(mode="json"),
            "summary": "原配置",
            "recommendation_summary": "推荐配置",
        },
    )
    published = await domain.get_run(plan.id)
    plan_view = await domain.get_plan(obj.id, published.result_ref.version)
    run = await domain.generate(
        obj.id,
        GenerateRequest(
            expected_version=obj.version,
            plan_version=plan_view.version,
            candidate="original",
            confirmed_config_digest=plan_view.original.config_digest,
            request_key=uuid4(),
        ),
    )
    claim = await domain.claim_run("test")
    await domain.publish_run(
        claim.id, claim.lease_token, {"questions": [question(i) for i in range(count)]}
    )
    result = await domain.get_run(run.id)
    rev = await domain.get_revision(obj.id, result.result_ref.id)
    return await domain.detail(obj.id), rev


async def test_durable_plan_replay_optimistic_conflict_and_cancel(domain):
    obj = await domain.create(SetCreate(config=PracticeConfig(topic="事务"), request_key=uuid4()))
    body = PlanRequest(expected_version=obj.version, request_key=uuid4())
    run = await domain.plan(obj.id, body)
    with pytest.raises(ConflictError):
        await domain.plan(obj.id, body)
    assert (await domain.lookup_run(body.request_key)).id == run.id
    cancelled = await domain.cancel(run.id)
    assert cancelled.status == "cancelled"
    assert (await domain.plan(obj.id, body)).id == run.id
    with pytest.raises(ConflictError):
        await domain.plan(obj.id, body.model_copy(update={"expected_version": 2}))
    with pytest.raises(ConflictError):
        await domain.patch(obj.id, SetPatch(expected_version=8, title="新标题"))


async def test_attempt_draft_submission_replay_report_and_immutable_revision(domain):
    obj, rev = await prepared(domain)
    start = AttemptCreate(expected_version=obj.version, revision_id=rev.id, request_key=uuid4())
    attempt = await domain.create_attempt(obj.id, start)
    assert (await domain.create_attempt(obj.id, start)).id == attempt.id
    first = rev.questions[0]
    saved = await domain.save_answer(
        attempt.id,
        first.question_id,
        AnswerSave(
            expected_version=attempt.version,
            answer=SingleAnswer(type="single_choice", option_id="A"),
        ),
    )
    request = SubmitRequest(
        expected_version=saved.version, answer_version=saved.answers[0].version, request_key=uuid4()
    )
    submitted = await domain.submit(attempt.id, first.question_id, request)
    assert submitted.grades[0].level == "correct"
    assert (
        await domain.submit(attempt.id, first.question_id, request)
    ).submission_id == submitted.submission_id
    report = await domain.report(attempt.id)
    assert report.submitted_count == report.graded_count == 1 and report.score is None
    edited = first.model_copy(update={"stem": "编辑后新的题干"})
    new = await domain.edit_question(obj.id, first.question_id, obj.version, edited)
    assert new.id != rev.id
    assert (await domain.get_attempt(attempt.id)).questions[0].stem == first.stem
    with pytest.raises(ConflictError):
        await domain.save_answer(
            attempt.id,
            first.question_id,
            AnswerSave(
                expected_version=attempt.version,
                answer=SingleAnswer(type="single_choice", option_id="B"),
            ),
        )
    current = await domain.get_attempt(attempt.id)
    completed = await domain.complete(attempt.id, current.version)
    assert completed.status == "completed"
    with pytest.raises(ConflictError):
        await domain.save_answer(
            attempt.id,
            first.question_id,
            AnswerSave(
                expected_version=completed.version,
                answer=SingleAnswer(type="single_choice", option_id="B"),
            ),
        )


async def test_late_lease_fencing_retry_and_deletion(domain):
    obj = await domain.create(SetCreate(config=PracticeConfig(topic="事务"), request_key=uuid4()))
    run = await domain.plan(obj.id, PlanRequest(expected_version=obj.version, request_key=uuid4()))
    claim = await domain.claim_run("old")
    old_token = claim.lease_token
    async with domain.sessions.begin() as session:
        persisted = await session.get(PracticeRun, run.id)
        persisted.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert await domain.expire_runs() == 1
    assert not await domain.heartbeat(run.id, old_token)
    await domain.retry(
        run.id, RetryRequest(request_key=run.request_key, input_digest=run.input_digest)
    )
    claimed = await domain.claim_run("new")
    assert claimed.lease_token != old_token and claimed.attempt_count == 2
    assert not await domain.publish_run(run.id, old_token, {})
    await domain.delete(obj.id, obj.version)
    assert not await domain.publish_run(run.id, claimed.lease_token, {})
    with pytest.raises(NotFoundError):
        await domain.get_run(run.id)


async def test_cross_owner_isolation_and_empty_preview(domain):
    obj, rev = await prepared(domain, 1)
    outsider = PracticeService(domain.sessions, uuid4(), domain.settings)
    for action in (
        outsider.detail(obj.id),
        outsider.get_revision(obj.id, rev.id),
        outsider.get_plan(obj.id, 1),
    ):
        with pytest.raises(NotFoundError):
            await action
    zero = await domain.edit_question(obj.id, rev.questions[0].question_id, obj.version, None)
    assert zero.questions == []
    current = await domain.detail(obj.id)
    with pytest.raises(ValidationAppError):
        await domain.create_attempt(
            obj.id,
            AttemptCreate(
                expected_version=current.version, revision_id=zero.id, request_key=uuid4()
            ),
        )


async def test_failed_generation_preserves_previous_revision_and_replay(domain):
    obj, rev = await prepared(domain)
    body = RegenerateRequest(
        expected_version=obj.version, base_revision_id=rev.id, request_key=uuid4()
    )
    run = await domain.regenerate(obj.id, body)
    claimed = await domain.claim_run("test")
    await domain.fail_run(claimed.id, claimed.lease_token, "PRACTICE_GENERATION_INVALID", False)
    assert (await domain.detail(obj.id)).revision.id == rev.id
    assert (await domain.regenerate(obj.id, body)).id == run.id


@pytest.mark.parametrize("retryable", [False, True])
async def test_failed_run_persists_retry_decision_and_enforces_retry_endpoint(domain, retryable):
    obj = await domain.create(SetCreate(config=PracticeConfig(topic="事务"), request_key=uuid4()))
    run = await domain.plan(obj.id, PlanRequest(expected_version=obj.version, request_key=uuid4()))
    claim = await domain.claim_run("retry-policy-test")
    assert await domain.fail_run(
        run.id, claim.lease_token, "PRACTICE_PROVIDER_UNAVAILABLE", retryable
    )
    restored = await domain.get_run(run.id)
    assert restored.status == "failed" and restored.retryable is retryable
    request = RetryRequest(request_key=run.request_key, input_digest=run.input_digest)
    if retryable:
        retried = await domain.retry(run.id, request)
        assert retried.status == "pending" and retried.id == run.id
    else:
        with pytest.raises(ConflictError) as failure:
            await domain.retry(run.id, request)
        assert failure.value.error_key == "PRACTICE_RETRY_UNAVAILABLE"
        assert (await domain.get_run(run.id)).status == "failed"


async def material_fixture(domain):
    from xuemian_ai.document_processing.models import (
        BackgroundTask,
        DocumentChunk,
        DocumentProcessingVersion,
        VectorIndexProfile,
    )
    from xuemian_ai.file_management.models import (
        FileAsset,
        FilePolicyVersion,
        KnowledgeBaseFile,
        StoredObject,
    )
    from xuemian_ai.file_management.policy import DEFAULT_RULES
    from xuemian_ai.knowledge_bases.models import KnowledgeBase

    async with domain.sessions.begin() as session:
        kb = KnowledgeBase(owner_user_id=domain.owner, name="Synthetic source", is_default=False)
        policy = await session.scalar(select(FilePolicyVersion).limit(1))
        if policy is None:
            policy = FilePolicyVersion(version=1, status="published", rules=DEFAULT_RULES)
            session.add(policy)
            await session.flush()
        stored = StoredObject(
            storage_domain="documents",
            sha256=uuid4().hex * 2,
            byte_size=80,
            detected_mime="text/plain",
            bucket="synthetic-only",
            object_key=uuid4().hex,
            status="available",
            reference_count=1,
        )
        profile = VectorIndexProfile(
            profile_key=uuid4().hex,
            provider="deterministic",
            model="synthetic",
            dimensions=1024,
            distance="Cosine",
            collection="synthetic-only",
            schema_version="v1",
        )
        session.add_all([kb, stored, profile])
        await session.flush()
        asset = FileAsset(
            owner_user_id=domain.owner,
            stored_object_id=stored.id,
            purpose="knowledge_document",
            original_filename="synthetic.txt",
            detected_mime="text/plain",
            byte_size=80,
            validation_status="available",
            policy_version_id=policy.id,
        )
        session.add(asset)
        await session.flush()
        binding = KnowledgeBaseFile(
            knowledge_base_id=kb.id,
            file_asset_id=asset.id,
            display_name="synthetic.txt",
            processing_status="succeeded",
            resource_version=1,
        )
        task = BackgroundTask(
            user_id=domain.owner,
            file_asset_id=asset.id,
            status="succeeded",
            next_attempt_at=datetime.now(UTC),
            input_generation=1,
        )
        session.add_all([binding, task])
        await session.flush()
        version = DocumentProcessingVersion(
            user_id=domain.owner,
            file_asset_id=asset.id,
            task_id=task.id,
            profile_id=profile.id,
            version_number=1,
            status="active",
            parser_version="synthetic",
            chunk_strategy_version="synthetic",
            ocr_strategy_version="synthetic",
        )
        session.add(version)
        await session.flush()
        chunk = DocumentChunk(
            processing_version_id=version.id,
            file_asset_id=asset.id,
            user_id=domain.owner,
            ordinal=0,
            content="Synthetic private original content",
            content_digest=uuid4().hex * 2,
            source_kind="native",
            paragraph_start=1,
            paragraph_end=1,
            search_vector="",
        )
        session.add(chunk)
        await session.flush()
    config = PracticeConfig(
        source_mode="materials",
        knowledge_base_id=kb.id,
        file_ids=[binding.id],
        topic="事务",
        question_count=1,
        question_types={"single_choice": 1},
    )
    obj = await domain.create(SetCreate(config=config, request_key=uuid4()))
    q = question()
    q["source_refs"] = [
        {
            "source_id": "1",
            "file_id": str(binding.id),
            "file_asset_id": str(asset.id),
            "processing_version_id": str(version.id),
            "chunk_id": str(chunk.id),
            "display_name": binding.display_name,
            "page_start": None,
            "page_end": None,
            "paragraph_start": 1,
            "paragraph_end": 1,
        }
    ]
    async with domain.sessions.begin() as session:
        persisted = await domain._set(session, obj.id, True)
        rev = await domain._new_revision(
            session,
            persisted,
            [q],
            persisted.config,
            persisted.effective_context,
            persisted.source_snapshot,
            "generate",
        )
    return await domain.detail(obj.id), rev, binding.id, version.id


@pytest.mark.parametrize("revoke", ["delete", "move", "version"])
async def test_sources_revoked_stop_execution_and_hide_original_history(domain, revoke):
    from xuemian_ai.document_processing.models import DocumentProcessingVersion
    from xuemian_ai.file_management.models import KnowledgeBaseFile
    from xuemian_ai.knowledge_bases.models import KnowledgeBase

    obj, rev, file_id, version_id = await material_fixture(domain)
    qid = UUID(rev.questions[0]["question_id"])
    preview = await domain.source_preview(obj.id, rev.id, qid, "1")
    assert preview.available and preview.evidence == "Synthetic private original content"
    attempt = await domain.create_attempt(
        obj.id, AttemptCreate(expected_version=obj.version, request_key=uuid4(), revision_id=rev.id)
    )
    run = await domain.regenerate(
        obj.id,
        RegenerateRequest(
            expected_version=obj.version, request_key=uuid4(), base_revision_id=rev.id
        ),
    )
    claim = await domain.claim_run("revoke-test")
    async with domain.sessions.begin() as session:
        binding = await session.get(KnowledgeBaseFile, file_id)
        if revoke == "delete":
            binding.deleted_at = datetime.now(UTC)
        elif revoke == "move":
            kb = KnowledgeBase(owner_user_id=domain.owner, name="Moved", is_default=False)
            session.add(kb)
            await session.flush()
            binding.knowledge_base_id = kb.id
        else:
            version = await session.get(DocumentProcessingVersion, version_id)
            version.status = "retired"
            session.add(
                DocumentProcessingVersion(
                    user_id=version.user_id,
                    file_asset_id=version.file_asset_id,
                    task_id=version.task_id,
                    profile_id=version.profile_id,
                    version_number=2,
                    status="active",
                    parser_version="new-synthetic",
                    chunk_strategy_version="new",
                    ocr_strategy_version="new",
                )
            )
    assert not (await domain.get_revision(obj.id, rev.id)).source_available
    preview = await domain.source_preview(obj.id, rev.id, qid, "1")
    assert not preview.available and preview.evidence is None
    history = await domain.get_attempt(attempt.id)
    assert history.questions[0].stem == rev.questions[0]["stem"] and not history.source_available
    with pytest.raises(ConflictError):
        await domain.heartbeat(run.id, claim.lease_token)
    with pytest.raises(ConflictError):
        await domain.publish_run(run.id, claim.lease_token, {"questions": rev.questions})
    outsider = PracticeService(domain.sessions, uuid4(), domain.settings)
    with pytest.raises(NotFoundError):
        await outsider.source_preview(obj.id, rev.id, qid, "1")


async def test_subjective_async_grade_regrade_preserves_history_and_feedback(domain):
    from xuemian_ai.practice.schemas import FeedbackRequest, TextAnswer

    config = PracticeConfig(topic="事务", question_count=1, question_types={"short_answer": 1})
    obj = await domain.create(SetCreate(config=config, request_key=uuid4()))
    q = question()
    q.pop("options")
    q.update(type="short_answer", answer=["原子性"])
    async with domain.sessions.begin() as session:
        persisted = await domain._set(session, obj.id, True)
        rev = await domain._new_revision(
            session, persisted, [q], persisted.config, persisted.effective_context, [], "generate"
        )
    obj = await domain.detail(obj.id)
    attempt = await domain.create_attempt(
        obj.id, AttemptCreate(expected_version=obj.version, request_key=uuid4(), revision_id=rev.id)
    )
    qid = UUID(q["question_id"])
    saved = await domain.save_answer(
        attempt.id,
        qid,
        AnswerSave(
            expected_version=attempt.version, answer=TextAnswer(type="short_answer", text="原子性")
        ),
    )
    run = await domain.submit(
        attempt.id,
        qid,
        SubmitRequest(
            expected_version=saved.version,
            answer_version=saved.answers[0].version,
            request_key=uuid4(),
        ),
    )
    assert run.operation == "grade"
    current = await domain.get_attempt(attempt.id)
    with pytest.raises(ConflictError):
        await domain.complete(attempt.id, current.version)
    claim = await domain.claim_run("subjective-test")
    grade = {
        "level": "correct",
        "dimensions": [
            {
                "dimension_id": "correct",
                "level": "correct",
                "evidence": [{"quote": "原子性", "start": 0, "end": 3}],
                "score": 1,
                "max_score": 1,
            }
        ],
        "score": 1,
        "max_score": 1,
        "confidence": 0.6,
        "missing_points": [],
        "error_reasons": [],
        "suggestions": ["巩固事务原子性"],
    }
    await domain.publish_run(run.id, claim.lease_token, {"grade": grade})
    viewed = await domain.get_grade(run.submission_id, 1)
    assert viewed.low_confidence and viewed.version == 1
    await domain.feedback(FeedbackRequest(grade_id=viewed.id, feedback="helpful"))
    assert (await domain.get_grade(run.submission_id, 1)).feedback == "helpful"
    await domain.feedback(
        FeedbackRequest(revision_id=rev.id, question_id=qid, feedback="unhelpful")
    )
    assert (await domain.get_attempt(attempt.id)).question_feedback[str(qid)] == "unhelpful"
    current = await domain.get_attempt(attempt.id)
    await domain.complete(attempt.id, current.version)
    from xuemian_ai.practice.schemas import RegradeRequest

    regrade = await domain.regrade(
        run.submission_id, RegradeRequest(reason="低置信度重新评阅", request_key=uuid4())
    )
    claim = await domain.claim_run("regrade-test")
    await domain.publish_run(regrade.id, claim.lease_token, {"grade": {**grade, "confidence": 0.9}})
    assert (await domain.get_grade(run.submission_id, 1)).confidence == 0.6
    assert (await domain.get_grade(run.submission_id, 2)).confidence == 0.9
    history = await domain.get_attempt(attempt.id)
    assert len(history.submissions[0].grades) == 2


async def test_concurrent_draft_save_has_one_winner_and_cancel_fences_publication(domain):
    import asyncio

    obj, rev = await prepared(domain, 1)
    attempt = await domain.create_attempt(
        obj.id, AttemptCreate(expected_version=obj.version, revision_id=rev.id, request_key=uuid4())
    )
    qid = rev.questions[0].question_id
    results = await asyncio.gather(
        domain.save_answer(
            attempt.id,
            qid,
            AnswerSave(
                expected_version=attempt.version,
                answer=SingleAnswer(type="single_choice", option_id="A"),
            ),
        ),
        domain.save_answer(
            attempt.id,
            qid,
            AnswerSave(
                expected_version=attempt.version,
                answer=SingleAnswer(type="single_choice", option_id="B"),
            ),
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(result, ConflictError) for result in results) == 1, [
        type(result).__name__ for result in results
    ]
    restored = await domain.get_attempt(attempt.id)
    assert restored.version == attempt.version + 1 and len(restored.answers) == 1
    request = RegenerateRequest(
        expected_version=obj.version, base_revision_id=rev.id, request_key=uuid4()
    )
    run = await domain.regenerate(obj.id, request)
    # A fresh repository instance recovers the persisted pending operation after worker restart.
    replacement_worker = PracticeService(domain.sessions, UUID(int=0), domain.settings)
    claimed = await replacement_worker.claim_run("restarted-worker")
    assert claimed.id == run.id
    assert (await domain.cancel(run.id)).status == "cancel_requested"
    assert not await domain.publish_run(
        run.id,
        claimed.lease_token,
        {"questions": [q.model_dump(mode="json") for q in rev.questions]},
    )
    assert (await domain.get_run(run.id)).status == "cancelled"
    assert (await domain.detail(obj.id)).revision.id == rev.id


async def test_disabled_owner_cannot_call_model_or_publish(domain):
    obj = await domain.create(SetCreate(config=PracticeConfig(topic="事务"), request_key=uuid4()))
    run = await domain.plan(obj.id, PlanRequest(expected_version=obj.version, request_key=uuid4()))
    claim = await domain.claim_run("owner-test")
    async with domain.sessions.begin() as session:
        user = await session.get(User, domain.owner)
        user.status = "disabled"
    with pytest.raises(NotFoundError):
        await domain.heartbeat(run.id, claim.lease_token)
    assert not await domain.publish_run(run.id, claim.lease_token, {})
    saved = await domain.get_run(run.id)
    assert saved.status == saved.stage == "failed" and saved.error_key == "PRACTICE_NOT_FOUND"


async def test_idempotence_preserves_profile_field_presence(domain):
    key = uuid4()
    omitted = SetCreate(config=PracticeConfig(topic="事务"), request_key=key)
    original = await domain.create(omitted)
    assert (await domain.create(omitted)).id == original.id
    cleared = SetCreate(config=PracticeConfig(topic="事务", target_job=None), request_key=key)
    with pytest.raises(ConflictError):
        await domain.create(cleared)


async def test_objective_submission_key_cannot_be_reused_for_model_operation(domain):
    obj, rev = await prepared(domain, 1)
    attempt = await domain.create_attempt(
        obj.id, AttemptCreate(expected_version=obj.version, request_key=uuid4(), revision_id=rev.id)
    )
    qid = rev.questions[0].question_id
    saved = await domain.save_answer(
        attempt.id,
        qid,
        AnswerSave(
            expected_version=attempt.version,
            answer=SingleAnswer(type="single_choice", option_id="A"),
        ),
    )
    key = uuid4()
    await domain.submit(
        attempt.id,
        qid,
        SubmitRequest(
            expected_version=saved.version, answer_version=saved.answers[0].version, request_key=key
        ),
    )
    with pytest.raises(ConflictError):
        await domain.plan(obj.id, PlanRequest(expected_version=obj.version, request_key=key))


async def test_generated_set_preserves_profile_presence_and_clear_requires_new_plan(domain):
    from xuemian_ai.profiles.models import UserProfile

    async with domain.sessions.begin() as session:
        session.add(UserProfile(user_id=domain.owner, target_job="Java工程师"))
    obj, rev = await prepared(domain, 1)
    assert obj.profile_override_fields == []
    assert rev.effective_context["values"]["target_job"] == "Java工程师"
    cleared = await domain.patch(
        obj.id,
        SetPatch(
            expected_version=obj.version,
            config=PracticeConfig(
                topic="事务", target_job=None, question_count=1, question_types={"single_choice": 1}
            ),
        ),
    )
    assert cleared.profile_override_fields == ["target_job"]
    restored = await domain.detail(obj.id)
    assert restored.profile_override_fields == ["target_job"] and restored.config.target_job is None
    with pytest.raises(ConflictError):
        await domain.regenerate(
            obj.id,
            RegenerateRequest(
                expected_version=cleared.version, base_revision_id=rev.id, request_key=uuid4()
            ),
        )


@pytest.mark.parametrize("original_explicit", [False, True])
@pytest.mark.parametrize("recommended_clear", [False, True])
async def test_recommended_candidate_preserves_omitted_profile_and_explicit_clear(
    domain, original_explicit, recommended_clear
):
    from xuemian_ai.practice.service import config_dump
    from xuemian_ai.profiles.models import UserProfile

    async with domain.sessions.begin() as session:
        session.add(UserProfile(user_id=domain.owner, target_job="ProfileJava"))
    values = {"topic": "事务", "question_count": 1, "question_types": {"single_choice": 1}}
    if original_explicit:
        values["target_job"] = "ExplicitJava"
    config = PracticeConfig.model_validate(values)
    obj = await domain.create(SetCreate(config=config, request_key=uuid4()))
    run = await domain.plan(obj.id, PlanRequest(expected_version=obj.version, request_key=uuid4()))
    claim = await domain.claim_run("recommendation-test")
    candidate = config_dump(config)
    candidate.pop("target_job", None)
    if recommended_clear:
        candidate["target_job"] = None
    await domain.publish_run(
        run.id,
        claim.lease_token,
        {
            "recommended_config": candidate,
            "summary": "原配置",
            "recommendation_summary": "推荐配置",
        },
    )
    plan = await domain.get_plan(obj.id, 1)
    effective = plan.recommended.effective_context
    expected = None if recommended_clear else "ExplicitJava" if original_explicit else "ProfileJava"
    assert effective["values"]["target_job"] == expected
    assert effective["sources"]["target_job"] == (
        "explicit" if original_explicit or recommended_clear else "profile"
    )
    if original_explicit and not recommended_clear:
        assert plan.recommended.config.target_job == "ExplicitJava"


async def test_file_rename_keeps_fixed_source_authorized(domain):
    from xuemian_ai.file_management.models import KnowledgeBaseFile

    obj, rev, file_id, _ = await material_fixture(domain)
    async with domain.sessions.begin() as session:
        binding = await session.get(KnowledgeBaseFile, file_id)
        binding.display_name = "renamed-synthetic.txt"
        binding.resource_version += 1
    assert (await domain.get_revision(obj.id, rev.id)).source_available
    assert (
        await domain.source_preview(obj.id, rev.id, UUID(rev.questions[0]["question_id"]), "1")
    ).available
    run = await domain.regenerate(
        obj.id,
        RegenerateRequest(
            expected_version=obj.version, base_revision_id=rev.id, request_key=uuid4()
        ),
    )
    claim = await domain.claim_run("rename-test")
    assert await domain.heartbeat(run.id, claim.lease_token)
    assert await domain.publish_run(run.id, claim.lease_token, {"questions": rev.questions})
