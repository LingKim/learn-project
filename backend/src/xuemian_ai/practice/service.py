import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from pydantic import TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from xuemian_ai.accounts.models import User
from xuemian_ai.core.errors import ConflictError, NotFoundError, ValidationAppError
from xuemian_ai.core.responses import PageResponse, page_response
from xuemian_ai.document_processing.models import DocumentChunk, DocumentProcessingVersion
from xuemian_ai.file_management.models import FileAsset, KnowledgeBaseFile
from xuemian_ai.knowledge_bases.models import KnowledgeBase
from xuemian_ai.practice.models import (
    PracticeAnswer,
    PracticeAttempt,
    PracticeFeedback,
    PracticeGrade,
    PracticePlan,
    PracticeRevision,
    PracticeRun,
    PracticeSet,
    PracticeSubmission,
)
from xuemian_ai.practice.schemas import (
    AnswerSave,
    AnswerValue,
    AnswerView,
    AttemptCreate,
    AttemptView,
    FeedbackRequest,
    FeedbackView,
    GenerateRequest,
    GradePayload,
    GradeView,
    PlanCandidate,
    PlanRequest,
    PlanView,
    PracticeConfig,
    QuestionSnapshot,
    RegenerateRequest,
    RegradeRequest,
    ReportLearningAsset,
    ReportLearningReview,
    ReportQuestion,
    ReportView,
    ResultRef,
    RetryRequest,
    RevisionView,
    RubricDimension,
    RunView,
    SetCreate,
    SetDetail,
    SetPatch,
    SetView,
    SourcePreview,
    SourceRef,
    SubmissionGradeView,
    SubmitRequest,
    TopicReport,
)
from xuemian_ai.profiles.models import UserProfile

ACTIVE_RUNS = ("pending", "processing", "cancel_requested")
PROFILE_FIELDS = (
    "target_job",
    "experience_months",
    "target_level",
    "target_skills",
    "focus_topics",
    "learning_goal",
    "preferred_language",
)


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
        ).encode()
    ).hexdigest()


def config_dump(config: PracticeConfig) -> dict[str, Any]:
    data = config.model_dump(mode="json")
    for field in (*PROFILE_FIELDS, "learning_target"):
        if field not in config.model_fields_set:
            data.pop(field, None)
    return data


def conflict(key: str = "PRACTICE_VERSION_CONFLICT") -> ConflictError:
    return ConflictError("练习状态已变化，请重新读取后操作", error_key=key)


def version_check(actual: int, expected: int) -> None:
    if actual != expected:
        raise conflict()


def run_view(run: PracticeRun) -> RunView:
    return RunView.model_validate({key: getattr(run, key) for key in RunView.model_fields})


class PracticeService:
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], owner_user_id: UUID, settings: Any = None
    ) -> None:
        self.sessions, self.owner, self.settings = sessions, owner_user_id, settings

    async def _set(self, session: AsyncSession, set_id: UUID, lock: bool = False) -> PracticeSet:
        if lock:
            from xuemian_ai.learning_assets.service import owner_lock

            await owner_lock(session, self.owner)
        query = select(PracticeSet).where(
            PracticeSet.id == set_id,
            PracticeSet.owner_user_id == self.owner,
            PracticeSet.deleted_at.is_(None),
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        obj = await session.scalar(query)
        if not obj:
            raise NotFoundError(error_key="PRACTICE_NOT_FOUND")
        return obj

    async def _attempt(
        self, session: AsyncSession, attempt_id: UUID, lock: bool = False
    ) -> PracticeAttempt:
        obj = await session.scalar(
            select(PracticeAttempt).where(
                PracticeAttempt.id == attempt_id, PracticeAttempt.owner_user_id == self.owner
            )
        )
        if not obj:
            raise NotFoundError(error_key="PRACTICE_NOT_FOUND")
        await self._set(session, obj.set_id, lock)
        if lock:
            obj = await session.scalar(
                select(PracticeAttempt)
                .where(PracticeAttempt.id == attempt_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            assert obj
        return obj

    async def _revision(
        self, session: AsyncSession, set_id: UUID, revision_id: UUID
    ) -> PracticeRevision:
        await self._set(session, set_id)
        obj = await session.scalar(
            select(PracticeRevision).where(
                PracticeRevision.id == revision_id,
                PracticeRevision.set_id == set_id,
                PracticeRevision.owner_user_id == self.owner,
            )
        )
        if not obj:
            raise NotFoundError(error_key="PRACTICE_NOT_FOUND")
        return obj

    async def _submission(self, session: AsyncSession, submission_id: UUID) -> PracticeSubmission:
        obj = await session.scalar(
            select(PracticeSubmission).where(
                PracticeSubmission.id == submission_id,
                PracticeSubmission.owner_user_id == self.owner,
            )
        )
        if not obj:
            raise NotFoundError(error_key="PRACTICE_NOT_FOUND")
        await self._attempt(session, obj.attempt_id)
        return obj

    async def _sources(self, session: AsyncSession, config: PracticeConfig) -> list[dict[str, Any]]:
        if config.source_mode == "general":
            return []
        kb = await session.scalar(
            select(KnowledgeBase)
            .where(
                KnowledgeBase.id == config.knowledge_base_id,
                KnowledgeBase.owner_user_id == self.owner,
                KnowledgeBase.deleted_at.is_(None),
            )
            .with_for_update(read=True)
        )
        if not kb:
            raise NotFoundError(error_key="PRACTICE_NOT_FOUND")
        query = (
            select(KnowledgeBaseFile, DocumentProcessingVersion)
            .join(FileAsset, KnowledgeBaseFile.file_asset_id == FileAsset.id)
            .join(
                DocumentProcessingVersion, DocumentProcessingVersion.file_asset_id == FileAsset.id
            )
            .where(
                KnowledgeBaseFile.knowledge_base_id == kb.id,
                KnowledgeBaseFile.deleted_at.is_(None),
                FileAsset.deleted_at.is_(None),
                FileAsset.owner_user_id == self.owner,
                FileAsset.validation_status == "available",
                DocumentProcessingVersion.status == "active",
                DocumentProcessingVersion.user_id == self.owner,
            )
        )
        if config.file_ids:
            query = query.where(KnowledgeBaseFile.id.in_(config.file_ids))
        query = query.with_for_update(
            read=True, of=(KnowledgeBaseFile, FileAsset, DocumentProcessingVersion)
        )
        rows = (await session.execute(query)).all()
        if config.file_ids and set(config.file_ids) != {file.id for file, _ in rows}:
            raise conflict("PRACTICE_SOURCE_CHANGED")
        if not rows:
            raise ValidationAppError(
                "资料没有可用解析版本", error_key="PRACTICE_EVIDENCE_INSUFFICIENT"
            )
        return [
            {
                "file_id": str(file.id),
                "file_asset_id": str(file.file_asset_id),
                "processing_version_id": str(version.id),
                "resource_version": file.resource_version,
                "knowledge_base_id": str(kb.id),
                "display_name": file.display_name,
            }
            for file, version in rows
        ]

    async def _source_available(
        self, session: AsyncSession, config: dict[str, Any], snapshot: list[dict[str, Any]]
    ) -> bool:
        if config.get("source_mode") == "general":
            return True
        # A fixed snapshot deliberately does not widen when new files enter the knowledge base.
        parsed = PracticeConfig.model_validate(config)
        fixed = parsed.model_copy(update={"file_ids": [UUID(str(s["file_id"])) for s in snapshot]})
        try:
            current = await self._sources(session, fixed)
            identity_fields = (
                "file_id",
                "file_asset_id",
                "processing_version_id",
                "knowledge_base_id",
            )
            return {tuple(str(item[field]) for field in identity_fields) for item in current} == {
                tuple(str(item[field]) for field in identity_fields) for item in snapshot
            }
        except (ConflictError, NotFoundError, ValidationAppError):
            return False

    async def _assert_sources(
        self, session: AsyncSession, config: dict[str, Any], snapshot: list[dict[str, Any]]
    ) -> None:
        if not await self._source_available(session, config, snapshot):
            raise conflict("PRACTICE_SOURCE_CHANGED")

    async def _effective(self, session: AsyncSession, config: PracticeConfig) -> dict[str, Any]:
        from xuemian_ai.practice.context import ensure_general_topic, resolve_context

        profile = await session.scalar(select(UserProfile).where(UserProfile.user_id == self.owner))
        defaults = {field: getattr(profile, field) for field in PROFILE_FIELDS} if profile else None
        if defaults is not None and profile is not None:
            defaults["version"] = profile.version
        overrides = {
            field: getattr(config, field)
            for field in PROFILE_FIELDS
            if field in config.model_fields_set
        }
        target = None
        if config.learning_target:
            from xuemian_ai.learning_assets.service import resolve_learning_target

            target = await resolve_learning_target(
                session,
                self.owner,
                config.learning_target.model_dump(mode="json"),
                config_dump(config),
            )
        effective = resolve_context(overrides, defaults, target.get("context") if target else None)
        if target:
            effective["learning_target"] = target
        ensure_general_topic(config.model_dump(mode="json"), effective)
        return effective

    async def _assert_learning_target(
        self, session: AsyncSession, config: dict[str, Any], context: dict[str, Any]
    ) -> None:
        if not config.get("learning_target"):
            return
        from xuemian_ai.learning_assets.service import resolve_learning_target

        current = await resolve_learning_target(
            session, self.owner, config["learning_target"], config
        )
        if digest(current) != digest(context.get("learning_target")):
            raise conflict("LEARNING_ASSET_SOURCE_CHANGED")

    async def _set_view(self, session: AsyncSession, obj: PracticeSet) -> SetView:
        return SetView(
            profile_override_fields=[
                field
                for field in PROFILE_FIELDS
                if obj.effective_context.get("sources", {}).get(field) == "explicit"
            ],
            id=obj.id,
            title=obj.title,
            config=PracticeConfig.model_validate(obj.config),
            version=obj.version,
            current_revision_id=obj.current_revision_id,
            source_available=await self._source_available(session, obj.config, obj.source_snapshot),
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

    async def create(self, body: SetCreate) -> SetView:
        fingerprint = digest({"title": body.title, "config": config_dump(body.config)})
        async with self.sessions.begin() as session:
            await self._key_lock(session, body.request_key)
            existing = await session.scalar(
                select(PracticeSet).where(
                    PracticeSet.owner_user_id == self.owner,
                    PracticeSet.request_key == body.request_key,
                )
            )
            if existing:
                if existing.deleted_at or existing.input_digest != fingerprint:
                    raise conflict("PRACTICE_KEY_CONFLICT")
                return await self._set_view(session, existing)
            source = await self._sources(session, body.config)
            effective = await self._effective(session, body.config)
            obj = PracticeSet(
                owner_user_id=self.owner,
                created_by=self.owner,
                updated_by=self.owner,
                title=body.title,
                config=config_dump(body.config),
                effective_context=effective,
                source_snapshot=source,
                request_key=body.request_key,
                input_digest=fingerprint,
            )
            session.add(obj)
            await session.flush()
            return await self._set_view(session, obj)

    async def list_sets(self, page: int, page_size: int) -> PageResponse[SetView]:
        async with self.sessions() as session:
            query = select(PracticeSet).where(
                PracticeSet.owner_user_id == self.owner, PracticeSet.deleted_at.is_(None)
            )
            total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
            rows = (
                await session.scalars(
                    query.order_by(PracticeSet.updated_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
            return page_response(
                [await self._set_view(session, obj) for obj in rows],
                page=page,
                page_size=page_size,
                total=total,
            )

    async def detail(self, set_id: UUID) -> SetDetail:
        async with self.sessions() as session:
            obj = await self._set(session, set_id)
            revision = (
                await self._revision(session, set_id, obj.current_revision_id)
                if obj.current_revision_id
                else None
            )
            attempts = (
                await session.scalars(
                    select(PracticeAttempt)
                    .where(PracticeAttempt.set_id == set_id)
                    .order_by(PracticeAttempt.created_at.desc())
                )
            ).all()
            return SetDetail(
                **(await self._set_view(session, obj)).model_dump(),
                revision=await self._revision_view(session, revision) if revision else None,
                attempts=[await self._attempt_view(session, a) for a in attempts],
            )

    async def patch(self, set_id: UUID, body: SetPatch) -> SetView:
        async with self.sessions.begin() as session:
            obj = await self._set(session, set_id, True)
            version_check(obj.version, body.expected_version)
            if body.title is not None:
                obj.title = body.title
            if body.config is not None:
                old = PracticeConfig.model_validate(obj.config)
                new = body.config
                if (old.source_mode, old.knowledge_base_id, old.file_ids) != (
                    new.source_mode,
                    new.knowledge_base_id,
                    new.file_ids,
                ):
                    raise ValidationAppError(
                        "来源范围固定，请创建新练习", error_key="PRACTICE_CONFIG_INVALID"
                    )
                await self._assert_sources(session, obj.config, obj.source_snapshot)
                obj.config = config_dump(new)
                obj.effective_context = await self._effective(session, new)
            obj.version += 1
            await session.flush()
            await session.refresh(obj, attribute_names=["updated_at"])
            return await self._set_view(session, obj)

    async def delete(self, set_id: UUID, expected_version: int) -> None:
        async with self.sessions.begin() as session:
            obj = await self._set(session, set_id, True)
            version_check(obj.version, expected_version)
            obj.deleted_at, obj.deleted_by = datetime.now(UTC), self.owner
            obj.version += 1
            from xuemian_ai.learning_assets.projection import append_evidence_event

            await append_evidence_event(session, self.owner, "set_deleted", obj.id, obj.version)
            runs = (
                await session.scalars(
                    select(PracticeRun)
                    .where(PracticeRun.set_id == obj.id, PracticeRun.status.in_(ACTIVE_RUNS))
                    .with_for_update()
                )
            ).all()
            for run in runs:
                run.status = "cancelled" if run.status == "pending" else "cancel_requested"

    async def _key_lock(self, session: AsyncSession, key: UUID) -> None:
        # Serialize duplicate UUID requests without holding a transaction during model calls.
        lock_key = int(digest([str(self.owner), str(key)])[:15], 16)
        await session.execute(select(func.pg_advisory_xact_lock(lock_key)))

    async def _replay(
        self, session: AsyncSession, key: UUID, fingerprint: str
    ) -> PracticeRun | None:
        await self._key_lock(session, key)
        submission = await session.scalar(
            select(PracticeSubmission).where(
                PracticeSubmission.owner_user_id == self.owner,
                PracticeSubmission.request_key == key,
            )
        )
        if submission and submission.input_digest != fingerprint:
            raise conflict("PRACTICE_KEY_CONFLICT")
        run = await session.scalar(
            select(PracticeRun).where(
                PracticeRun.owner_user_id == self.owner, PracticeRun.request_key == key
            )
        )
        if run:
            if run.input_digest != fingerprint:
                raise conflict("PRACTICE_KEY_CONFLICT")
            if run.status in ACTIVE_RUNS:
                raise ConflictError(
                    f"任务处理中，任务编号 {run.id}", error_key="PRACTICE_RUN_PROCESSING"
                )
        return run

    def _enqueue(
        self,
        session: AsyncSession,
        obj: PracticeSet,
        operation: str,
        key: UUID,
        fingerprint: str,
        snapshot: dict[str, Any],
        submission_id: UUID | None = None,
    ) -> PracticeRun:
        run = PracticeRun(
            id=uuid4(),
            owner_user_id=self.owner,
            set_id=obj.id,
            operation=operation,
            request_key=key,
            input_digest=fingerprint,
            input_snapshot=snapshot,
            submission_id=submission_id,
        )
        session.add(run)
        return run

    async def plan(self, set_id: UUID, body: PlanRequest) -> RunView:
        fingerprint = digest(["plan", str(set_id), body.model_dump(mode="json")])
        async with self.sessions.begin() as session:
            obj = await self._set(session, set_id, True)
            previous = await self._replay(session, body.request_key, fingerprint)
            if previous:
                return run_view(previous)
            version_check(obj.version, body.expected_version)
            await self._assert_sources(session, obj.config, obj.source_snapshot)
            await self._assert_learning_target(session, obj.config, obj.effective_context)
            run = self._enqueue(
                session,
                obj,
                "plan",
                body.request_key,
                fingerprint,
                {
                    "config": obj.config,
                    "effective_context": obj.effective_context,
                    "source_snapshot": obj.source_snapshot,
                    "expected_version": obj.version,
                },
            )
            await session.flush()
            return run_view(run)

    async def get_plan(self, set_id: UUID, plan_version: int) -> PlanView:
        async with self.sessions() as session:
            await self._set(session, set_id)
            plan = await session.scalar(
                select(PracticePlan).where(
                    PracticePlan.set_id == set_id, PracticePlan.version == plan_version
                )
            )
            if not plan:
                raise NotFoundError(error_key="PRACTICE_NOT_FOUND")
            return self._plan_view(plan)

    @staticmethod
    def _plan_view(plan: PracticePlan) -> PlanView:
        return PlanView(
            id=plan.id,
            set_id=plan.set_id,
            version=plan.version,
            base_set_version=plan.base_set_version,
            original=PlanCandidate.model_validate(plan.candidates["original"]),
            recommended=PlanCandidate.model_validate(plan.candidates["recommended"]),
            suggestions=plan.suggestions,
        )

    async def generate(self, set_id: UUID, body: GenerateRequest) -> RunView:
        fingerprint = digest(["generate", str(set_id), body.model_dump(mode="json")])
        async with self.sessions.begin() as session:
            obj = await self._set(session, set_id, True)
            replay = await self._replay(session, body.request_key, fingerprint)
            if replay:
                return run_view(replay)
            version_check(obj.version, body.expected_version)
            plan = await session.scalar(
                select(PracticePlan).where(
                    PracticePlan.set_id == set_id, PracticePlan.version == body.plan_version
                )
            )
            if not plan or plan.base_set_version != obj.version:
                raise conflict("PRACTICE_PLAN_STALE")
            candidate = PlanCandidate.model_validate(plan.candidates[body.candidate])
            if candidate.config_digest != body.confirmed_config_digest:
                raise conflict("PRACTICE_PLAN_STALE")
            await self._assert_sources(session, obj.config, obj.source_snapshot)
            await self._assert_learning_target(
                session, config_dump(candidate.config), candidate.effective_context
            )
            selected_config = candidate.config.model_dump(mode="json")
            for field in PROFILE_FIELDS:
                if (
                    cast(dict[str, Any], candidate.effective_context.get("sources", {})).get(field)
                    != "explicit"
                ):
                    selected_config.pop(field, None)
            run = self._enqueue(
                session,
                obj,
                "generate",
                body.request_key,
                fingerprint,
                {
                    "config": selected_config,
                    "effective_context": candidate.effective_context,
                    "source_snapshot": obj.source_snapshot,
                    "expected_version": obj.version,
                    "plan_id": str(plan.id),
                },
            )
            await session.flush()
            return run_view(run)

    async def regenerate(self, set_id: UUID, body: RegenerateRequest) -> RunView:
        fingerprint = digest(["regenerate", str(set_id), body.model_dump(mode="json")])
        async with self.sessions.begin() as session:
            obj = await self._set(session, set_id, True)
            replay = await self._replay(session, body.request_key, fingerprint)
            if replay:
                return run_view(replay)
            version_check(obj.version, body.expected_version)
            rev = await self._revision(session, set_id, body.base_revision_id)
            if (
                obj.current_revision_id != rev.id
                or digest(PracticeConfig.model_validate(obj.config).model_dump(mode="json"))
                != digest(PracticeConfig.model_validate(rev.config).model_dump(mode="json"))
                or digest(obj.effective_context) != digest(rev.effective_context)
            ):
                raise conflict("PRACTICE_PLAN_STALE")
            if not rev.questions:
                raise ValidationAppError("请重新配置题量", error_key="PRACTICE_CONFIG_INVALID")
            questions = rev.questions
            if body.question_id:
                self._question(rev, body.question_id)
            await self._assert_sources(session, rev.config, rev.source_snapshot)
            await self._assert_learning_target(session, rev.config, rev.effective_context)
            counts: dict[str, int] = {}
            targets = [
                q
                for q in questions
                if not body.question_id or q["question_id"] == str(body.question_id)
            ]
            for q in targets:
                counts[str(q["type"])] = counts.get(str(q["type"]), 0) + 1
            config = dict(rev.config)
            config.update(question_count=len(targets), question_types=counts)
            if body.question_id:
                config["difficulty"] = targets[0]["difficulty"]
            run = self._enqueue(
                session,
                obj,
                "regenerate",
                body.request_key,
                fingerprint,
                {
                    "config": config,
                    "revision_config": rev.config,
                    "effective_context": rev.effective_context,
                    "source_snapshot": rev.source_snapshot,
                    "expected_version": obj.version,
                    "base_revision_id": str(rev.id),
                    "question_id": str(body.question_id) if body.question_id else None,
                    "questions": rev.questions,
                },
            )
            await session.flush()
            return run_view(run)

    async def _question_feedback(self, session: AsyncSession, revision_id: UUID) -> dict[str, Any]:
        rows = (
            await session.scalars(
                select(PracticeFeedback).where(
                    PracticeFeedback.owner_user_id == self.owner,
                    PracticeFeedback.revision_id == revision_id,
                )
            )
        ).all()
        return {str(row.question_id): row.feedback for row in rows}

    async def source_preview(
        self, set_id: UUID, revision_id: UUID, question_id: UUID, source_id: str
    ) -> SourcePreview:
        async with self.sessions() as session:
            revision = await self._revision(session, set_id, revision_id)
            question: QuestionSnapshot = TypeAdapter(QuestionSnapshot).validate_python(
                self._question(revision, question_id)
            )
            source = next((ref for ref in question.source_refs if ref.source_id == source_id), None)
            if not source:
                raise NotFoundError(error_key="PRACTICE_NOT_FOUND")
            available = await self._source_available(
                session, revision.config, revision.source_snapshot
            )
            chunk = (
                await session.scalar(
                    select(DocumentChunk).where(
                        DocumentChunk.id == source.chunk_id,
                        DocumentChunk.user_id == self.owner,
                        DocumentChunk.processing_version_id == source.processing_version_id,
                    )
                )
                if available
                else None
            )
            return SourcePreview(
                source=source,
                available=available and chunk is not None,
                evidence=chunk.content if chunk else None,
            )

    async def _revision_view(self, session: AsyncSession, rev: PracticeRevision) -> RevisionView:
        return RevisionView(
            id=rev.id,
            set_id=rev.set_id,
            version=rev.version,
            config=PracticeConfig.model_validate(rev.config),
            effective_context=rev.effective_context,
            questions=TypeAdapter(list[QuestionSnapshot]).validate_python(rev.questions),
            source_available=await self._source_available(session, rev.config, rev.source_snapshot),
            question_feedback=await self._question_feedback(session, rev.id),
            source_mode=PracticeConfig.model_validate(rev.config).source_mode,
            reason=rev.reason,
            created_at=rev.created_at,
        )

    async def get_revision(self, set_id: UUID, revision_id: UUID) -> RevisionView:
        async with self.sessions() as session:
            return await self._revision_view(
                session, await self._revision(session, set_id, revision_id)
            )

    @staticmethod
    def _question(revision: PracticeRevision, question_id: UUID) -> dict[str, Any]:
        for question in revision.questions:
            if str(question["question_id"]) == str(question_id):
                return question
        raise NotFoundError(error_key="PRACTICE_NOT_FOUND")

    async def _validate_refs(
        self,
        session: AsyncSession,
        questions: list[dict[str, Any]],
        config: dict[str, Any],
        sources: list[dict[str, Any]],
    ) -> None:
        await self._assert_sources(session, config, sources)
        if config.get("source_mode") == "general":
            if any(q.get("source_refs") for q in questions):
                raise ValidationAppError(
                    "通用题不能伪造资料引用", error_key="PRACTICE_GENERATION_INVALID"
                )
            return
        allowed = {str(s["file_id"]): s for s in sources}
        for question in questions:
            refs: list[SourceRef] = (
                TypeAdapter(QuestionSnapshot).validate_python(question).source_refs
            )
            if not refs:
                raise ValidationAppError(
                    "资料题必须具有来源", error_key="PRACTICE_GENERATION_INVALID"
                )
            for ref in refs:
                source = allowed.get(str(ref.file_id))
                if (
                    not source
                    or str(source["file_asset_id"]) != str(ref.file_asset_id)
                    or str(source["processing_version_id"]) != str(ref.processing_version_id)
                ):
                    raise conflict("PRACTICE_SOURCE_CHANGED")
                chunk = await session.scalar(
                    select(DocumentChunk).where(
                        DocumentChunk.id == ref.chunk_id,
                        DocumentChunk.file_asset_id == ref.file_asset_id,
                        DocumentChunk.processing_version_id == ref.processing_version_id,
                        DocumentChunk.user_id == self.owner,
                    )
                )
                if not chunk or (
                    ref.page_start,
                    ref.page_end,
                    ref.paragraph_start,
                    ref.paragraph_end,
                ) != (chunk.page_start, chunk.page_end, chunk.paragraph_start, chunk.paragraph_end):
                    raise ValidationAppError(
                        "引用定位无效", error_key="PRACTICE_GENERATION_INVALID"
                    )

    async def _new_revision(
        self,
        session: AsyncSession,
        obj: PracticeSet,
        questions: list[dict[str, Any]],
        config: dict[str, Any],
        context: dict[str, Any],
        sources: list[dict[str, Any]],
        reason: str,
        run: PracticeRun | None = None,
        manifest: dict[str, Any] | None = None,
    ) -> PracticeRevision:
        from xuemian_ai.practice.generation import validate_question_snapshots

        questions = validate_question_snapshots(questions)
        if config.get("learning_target"):
            from xuemian_ai.learning_assets.policy import concept_key

            concept = concept_key(str(context["learning_target"]["concept"]))
            if any(
                len(q["topics"]) != 1 or concept_key(q["topics"][0]) != concept for q in questions
            ):
                raise ValidationAppError(
                    "针对性练习题须仅考查目标知识点", error_key="PRACTICE_GENERATION_INVALID"
                )
        await self._validate_refs(session, questions, config, sources)
        normalized = [" ".join(str(q["stem"]).split()).casefold() for q in questions]
        if len(set(normalized)) != len(normalized) or len(
            {str(q["question_id"]) for q in questions}
        ) != len(questions):
            raise ValidationAppError("题目重复", error_key="PRACTICE_GENERATION_INVALID")
        number = (
            await session.scalar(
                select(func.max(PracticeRevision.version)).where(PracticeRevision.set_id == obj.id)
            )
            or 0
        ) + 1
        rev = PracticeRevision(
            id=uuid4(),
            owner_user_id=self.owner,
            set_id=obj.id,
            version=number,
            parent_revision_id=obj.current_revision_id,
            plan_id=UUID(str(run.input_snapshot["plan_id"]))
            if run and run.input_snapshot.get("plan_id")
            else None,
            questions=questions,
            config=config,
            effective_context=context,
            source_snapshot=sources,
            reason=reason,
            run_id=run.id if run else None,
            manifest=manifest or {},
        )
        session.add(rev)
        obj.current_revision_id = rev.id
        if reason == "generate":
            obj.config, obj.effective_context = config, context
        obj.version += 1
        await session.flush()
        return rev

    async def edit_question(
        self,
        set_id: UUID,
        question_id: UUID,
        expected_version: int,
        question: QuestionSnapshot | None,
    ) -> RevisionView:
        async with self.sessions.begin() as session:
            obj = await self._set(session, set_id, True)
            version_check(obj.version, expected_version)
            if not obj.current_revision_id:
                raise NotFoundError(error_key="PRACTICE_NOT_FOUND")
            rev = await self._revision(session, set_id, obj.current_revision_id)
            self._question(rev, question_id)
            if question and question.question_id != question_id:
                raise ValidationAppError("题目编号不能改变", error_key="PRACTICE_CONFIG_INVALID")
            if question:
                allowed = {digest(r) for q in rev.questions for r in q.get("source_refs", [])}
                if any(
                    digest(r.model_dump(mode="json")) not in allowed for r in question.source_refs
                ):
                    raise ValidationAppError(
                        "只能使用题集中已授权引用", error_key="PRACTICE_CONFIG_INVALID"
                    )
            # Explicit branch avoids changing other questions during a replacement.
            questions = [
                question.model_dump(mode="json")
                if str(q["question_id"]) == str(question_id) and question
                else q
                for q in rev.questions
                if question or str(q["question_id"]) != str(question_id)
            ]
            new = await self._new_revision(
                session,
                obj,
                questions,
                rev.config,
                rev.effective_context,
                rev.source_snapshot,
                "edit" if question else "delete",
            )
            return await self._revision_view(session, new)

    async def create_attempt(self, set_id: UUID, body: AttemptCreate) -> AttemptView:
        fingerprint = digest(["attempt", str(set_id), body.model_dump(mode="json")])
        async with self.sessions.begin() as session:
            obj = await self._set(session, set_id, True)
            await self._key_lock(session, body.request_key)
            old = await session.scalar(
                select(PracticeAttempt).where(
                    PracticeAttempt.owner_user_id == self.owner,
                    PracticeAttempt.request_key == body.request_key,
                )
            )
            if old:
                if old.input_digest != fingerprint:
                    raise conflict("PRACTICE_KEY_CONFLICT")
                return await self._attempt_view(session, old)
            version_check(obj.version, body.expected_version)
            rev = await self._revision(session, set_id, body.revision_id)
            if not rev.questions:
                raise ValidationAppError("题集为空，不能开始", error_key="PRACTICE_CONFIG_INVALID")
            await self._assert_sources(session, rev.config, rev.source_snapshot)
            attempt = PracticeAttempt(
                id=uuid4(),
                owner_user_id=self.owner,
                set_id=set_id,
                revision_id=rev.id,
                started_at=datetime.now(UTC),
                request_key=body.request_key,
                input_digest=fingerprint,
                current_question_id=UUID(str(rev.questions[0]["question_id"])),
            )
            session.add(attempt)
            await session.flush()
            return await self._attempt_view(session, attempt)

    async def _grade_view(self, session: AsyncSession, grade: PracticeGrade) -> GradeView:
        submission = await self._submission(session, grade.submission_id)
        attempt = await self._attempt(session, submission.attempt_id)
        revision = await self._revision(session, attempt.set_id, attempt.revision_id)
        payload = GradePayload.model_validate(grade.payload)
        feedback = await session.scalar(
            select(PracticeFeedback.feedback).where(
                PracticeFeedback.owner_user_id == self.owner, PracticeFeedback.grade_id == grade.id
            )
        )
        return GradeView(
            **payload.model_dump(),
            id=grade.id,
            submission_id=grade.submission_id,
            version=grade.version,
            low_confidence=payload.confidence < 0.7,
            feedback=cast(Literal["helpful", "unhelpful"] | None, feedback),
            rubric=TypeAdapter(list[RubricDimension]).validate_python(grade.rubric),
            topics=submission.question["topics"],
            source_mode=revision.config.get("source_mode", "general"),
            created_at=grade.created_at,
        )

    async def _submission_view(
        self, session: AsyncSession, sub: PracticeSubmission
    ) -> SubmissionGradeView:
        grades = (
            await session.scalars(
                select(PracticeGrade)
                .where(PracticeGrade.submission_id == sub.id)
                .order_by(PracticeGrade.version)
            )
        ).all()
        run = await session.scalar(
            select(PracticeRun)
            .where(PracticeRun.submission_id == sub.id)
            .order_by(PracticeRun.created_at.desc())
            .limit(1)
        )
        return SubmissionGradeView(
            submission_id=sub.id,
            question_id=sub.question_id,
            answer=TypeAdapter(AnswerValue).validate_python(sub.answer),
            answer_version=sub.answer_version,
            grades=[await self._grade_view(session, g) for g in grades],
            run=run_view(run) if run else None,
        )

    async def _attempt_view(self, session: AsyncSession, attempt: PracticeAttempt) -> AttemptView:
        rev = await self._revision(session, attempt.set_id, attempt.revision_id)
        answers = (
            await session.scalars(
                select(PracticeAnswer).where(PracticeAnswer.attempt_id == attempt.id)
            )
        ).all()
        submissions = (
            await session.scalars(
                select(PracticeSubmission)
                .where(PracticeSubmission.attempt_id == attempt.id)
                .order_by(PracticeSubmission.created_at)
            )
        ).all()
        return AttemptView(
            id=attempt.id,
            set_id=attempt.set_id,
            revision_id=rev.id,
            status=cast(Literal["active", "completed"], attempt.status),
            version=attempt.version,
            current_question_id=attempt.current_question_id,
            questions=TypeAdapter(list[QuestionSnapshot]).validate_python(rev.questions),
            answers=[
                AnswerView(
                    question_id=a.question_id,
                    version=a.version,
                    answer=TypeAdapter(AnswerValue).validate_python(a.answer),
                )
                for a in answers
            ],
            submissions=[await self._submission_view(session, s) for s in submissions],
            source_available=await self._source_available(session, rev.config, rev.source_snapshot),
            question_feedback=await self._question_feedback(session, rev.id),
            started_at=attempt.started_at,
            completed_at=attempt.completed_at,
        )

    async def get_attempt(self, attempt_id: UUID) -> AttemptView:
        async with self.sessions() as session:
            return await self._attempt_view(session, await self._attempt(session, attempt_id))

    @staticmethod
    def _active(attempt: PracticeAttempt) -> None:
        if attempt.status != "active":
            raise conflict("PRACTICE_ATTEMPT_COMPLETED")

    @staticmethod
    def _validate_answer(question: dict[str, Any], answer: AnswerValue) -> None:
        if question["type"] != answer.type:
            raise ValidationAppError("答案题型不匹配", error_key="PRACTICE_CONFIG_INVALID")
        options = {str(o["id"]) for o in question.get("options", [])}
        if answer.type == "single_choice" and answer.option_id not in options:
            raise ValidationAppError("选项无效", error_key="PRACTICE_CONFIG_INVALID")
        if answer.type == "multiple_choice" and (
            len(set(answer.option_ids)) != len(answer.option_ids)
            or not set(answer.option_ids) <= options
        ):
            raise ValidationAppError("选项无效", error_key="PRACTICE_CONFIG_INVALID")

    async def save_answer(
        self, attempt_id: UUID, question_id: UUID, body: AnswerSave
    ) -> AttemptView:
        async with self.sessions.begin() as session:
            attempt = await self._attempt(session, attempt_id, True)
            self._active(attempt)
            version_check(attempt.version, body.expected_version)
            rev = await self._revision(session, attempt.set_id, attempt.revision_id)
            self._validate_answer(self._question(rev, question_id), body.answer)
            if body.current_question_id:
                self._question(rev, body.current_question_id)
                attempt.current_question_id = body.current_question_id
            answer = await session.scalar(
                select(PracticeAnswer).where(
                    PracticeAnswer.attempt_id == attempt_id,
                    PracticeAnswer.question_id == question_id,
                )
            )
            if answer:
                answer.answer = body.answer.model_dump(mode="json")
                answer.version += 1
            else:
                session.add(
                    PracticeAnswer(
                        attempt_id=attempt_id,
                        question_id=question_id,
                        answer=body.answer.model_dump(mode="json"),
                    )
                )
            attempt.version += 1
            await session.flush()
            return await self._attempt_view(session, attempt)

    async def _save_grade(
        self,
        session: AsyncSession,
        sub: PracticeSubmission,
        payload: GradePayload,
        run: PracticeRun | None = None,
        manifest: dict[str, Any] | None = None,
    ) -> PracticeGrade:
        number = (
            await session.scalar(
                select(func.max(PracticeGrade.version)).where(PracticeGrade.submission_id == sub.id)
            )
            or 0
        ) + 1
        grade = PracticeGrade(
            id=uuid4(),
            owner_user_id=self.owner,
            submission_id=sub.id,
            version=number,
            payload=payload.model_dump(mode="json"),
            rubric=sub.question["rubric"],
            run_id=run.id if run else None,
            manifest=manifest or {},
        )
        session.add(grade)
        await session.flush()
        from xuemian_ai.learning_assets.projection import append_evidence_event

        await append_evidence_event(session, self.owner, "grade_published", grade.id, grade.version)
        return grade

    async def submit(
        self, attempt_id: UUID, question_id: UUID, body: SubmitRequest
    ) -> SubmissionGradeView | RunView:
        fingerprint = digest(
            ["submit", str(attempt_id), str(question_id), body.model_dump(mode="json")]
        )
        async with self.sessions.begin() as session:
            attempt = await self._attempt(session, attempt_id, True)
            await self._key_lock(session, body.request_key)
            old = await session.scalar(
                select(PracticeSubmission).where(
                    PracticeSubmission.owner_user_id == self.owner,
                    PracticeSubmission.request_key == body.request_key,
                )
            )
            if old:
                if old.input_digest != fingerprint:
                    raise conflict("PRACTICE_KEY_CONFLICT")
                run = await session.scalar(
                    select(PracticeRun).where(
                        PracticeRun.submission_id == old.id,
                        PracticeRun.request_key == body.request_key,
                    )
                )
                if run:
                    if run.status in ACTIVE_RUNS:
                        raise ConflictError(
                            f"任务处理中，任务编号 {run.id}", error_key="PRACTICE_RUN_PROCESSING"
                        )
                    return run_view(run)
                return await self._submission_view(session, old)
            existing_run = await session.scalar(
                select(PracticeRun).where(
                    PracticeRun.owner_user_id == self.owner,
                    PracticeRun.request_key == body.request_key,
                )
            )
            if existing_run:
                raise conflict("PRACTICE_KEY_CONFLICT")
            self._active(attempt)
            version_check(attempt.version, body.expected_version)
            rev = await self._revision(session, attempt.set_id, attempt.revision_id)
            await self._assert_sources(session, rev.config, rev.source_snapshot)
            question = self._question(rev, question_id)
            answer = await session.scalar(
                select(PracticeAnswer).where(
                    PracticeAnswer.attempt_id == attempt_id,
                    PracticeAnswer.question_id == question_id,
                )
            )
            if not answer:
                raise ValidationAppError("请先保存答案", error_key="PRACTICE_CONFIG_INVALID")
            version_check(answer.version, body.answer_version)
            parsed: AnswerValue = TypeAdapter(AnswerValue).validate_python(answer.answer)
            self._validate_answer(question, parsed)
            if parsed.type in ("short_answer", "code_text") and not parsed.text.strip():
                raise ValidationAppError("答案不能为空", error_key="PRACTICE_CONFIG_INVALID")
            sub = PracticeSubmission(
                id=uuid4(),
                owner_user_id=self.owner,
                attempt_id=attempt_id,
                question_id=question_id,
                answer_version=answer.version,
                answer=answer.answer,
                question=question,
                request_key=body.request_key,
                input_digest=fingerprint,
            )
            session.add(sub)
            await session.flush()
            from xuemian_ai.learning_assets.projection import append_evidence_event

            await append_evidence_event(
                session, self.owner, "submission_published", sub.id, sub.answer_version
            )
            attempt.version += 1
            if parsed.type in ("single_choice", "multiple_choice", "true_false"):
                from xuemian_ai.practice.grading import grade_objective

                await self._save_grade(session, sub, grade_objective(question, answer.answer))
                return await self._submission_view(session, sub)
            obj = await self._set(session, attempt.set_id)
            run = self._enqueue(
                session,
                obj,
                "grade",
                body.request_key,
                fingerprint,
                {
                    "config": rev.config,
                    "effective_context": rev.effective_context,
                    "source_snapshot": rev.source_snapshot,
                    "question": question,
                    "answer": answer.answer,
                    "submission_id": str(sub.id),
                },
                sub.id,
            )
            await session.flush()
            return run_view(run)

    async def regrade(self, submission_id: UUID, body: RegradeRequest) -> RunView:
        fingerprint = digest(["regrade", str(submission_id), body.model_dump(mode="json")])
        async with self.sessions.begin() as session:
            sub = await self._submission(session, submission_id)
            attempt = await self._attempt(session, sub.attempt_id, True)
            replay = await self._replay(session, body.request_key, fingerprint)
            if replay:
                return run_view(replay)
            if sub.question["type"] not in ("short_answer", "code_text"):
                raise ValidationAppError(
                    "客观题不需要模型重评", error_key="PRACTICE_CONFIG_INVALID"
                )
            rev = await self._revision(session, attempt.set_id, attempt.revision_id)
            await self._assert_sources(session, rev.config, rev.source_snapshot)
            obj = await self._set(session, attempt.set_id)
            run = self._enqueue(
                session,
                obj,
                "regrade",
                body.request_key,
                fingerprint,
                {
                    "config": rev.config,
                    "effective_context": rev.effective_context,
                    "source_snapshot": rev.source_snapshot,
                    "question": sub.question,
                    "answer": sub.answer,
                    "submission_id": str(sub.id),
                    "reason": body.reason,
                },
                sub.id,
            )
            await session.flush()
            return run_view(run)

    async def get_grade(self, submission_id: UUID, grade_version: int) -> GradeView:
        async with self.sessions() as session:
            await self._submission(session, submission_id)
            grade = await session.scalar(
                select(PracticeGrade).where(
                    PracticeGrade.submission_id == submission_id,
                    PracticeGrade.version == grade_version,
                    PracticeGrade.owner_user_id == self.owner,
                )
            )
            if not grade:
                raise NotFoundError(error_key="PRACTICE_NOT_FOUND")
            return await self._grade_view(session, grade)

    async def complete(self, attempt_id: UUID, expected_version: int) -> AttemptView:
        async with self.sessions.begin() as session:
            attempt = await self._attempt(session, attempt_id, True)
            self._active(attempt)
            version_check(attempt.version, expected_version)
            pending = await session.scalar(
                select(PracticeRun.id)
                .join(PracticeSubmission, PracticeRun.submission_id == PracticeSubmission.id)
                .where(
                    PracticeSubmission.attempt_id == attempt_id,
                    PracticeRun.operation == "grade",
                    PracticeRun.status.in_(ACTIVE_RUNS),
                )
                .limit(1)
            )
            if pending:
                raise conflict("PRACTICE_RUN_PROCESSING")
            attempt.status, attempt.completed_at = "completed", datetime.now(UTC)
            attempt.version += 1
            await session.flush()
            from xuemian_ai.learning_assets.projection import append_evidence_event

            await append_evidence_event(
                session, self.owner, "attempt_completed", attempt.id, attempt.version
            )
            return await self._attempt_view(session, attempt)

    async def report(self, attempt_id: UUID) -> ReportView:
        view = await self.get_attempt(attempt_id)
        async with self.sessions() as session:
            revision = await self._revision(session, view.set_id, view.revision_id)
            from xuemian_ai.learning_assets.models import LearningReview, Weakness, WeaknessEvidence
            from xuemian_ai.learning_assets.service import evidence_available

            linked = (
                await session.scalars(
                    select(Weakness)
                    .join(WeaknessEvidence, WeaknessEvidence.weakness_id == Weakness.id)
                    .where(
                        Weakness.owner_user_id == self.owner,
                        Weakness.deleted_at.is_(None),
                        WeaknessEvidence.owner_user_id == self.owner,
                        WeaknessEvidence.attempt_id == attempt_id,
                        WeaknessEvidence.superseded.is_(False),
                        WeaknessEvidence.ignored.is_(False),
                    )
                    .distinct()
                    .order_by(Weakness.id)
                )
            ).all()
            assets = []
            for asset in linked:
                evidence = (
                    await session.scalars(
                        select(WeaknessEvidence).where(
                            WeaknessEvidence.weakness_id == asset.id,
                            WeaknessEvidence.owner_user_id == self.owner,
                            WeaknessEvidence.attempt_id == attempt_id,
                            WeaknessEvidence.superseded.is_(False),
                            WeaknessEvidence.ignored.is_(False),
                        )
                    )
                ).all()
                available = any(
                    [
                        await evidence_available(session, self.owner, asset, item)
                        for item in evidence
                    ]
                )
                assets.append(
                    ReportLearningAsset(
                        id=asset.id,
                        title=asset.title,
                        decision=cast(
                            Literal["pending", "confirmed", "ignored", "revoked"], asset.decision
                        ),
                        mastery_state=cast(
                            Literal["to_learn", "learning", "to_verify", "mastered"],
                            asset.mastery_state,
                        ),
                        source_available=available,
                    )
                )
            review = await session.scalar(
                select(LearningReview)
                .where(
                    LearningReview.attempt_id == attempt_id,
                    LearningReview.owner_user_id == self.owner,
                )
                .order_by(LearningReview.version.desc())
                .limit(1)
            )
            review_view = (
                ReportLearningReview.model_validate(
                    {key: getattr(review, key) for key in ReportLearningReview.model_fields}
                )
                if review
                else None
            )
            if review_view:
                review_view.source_available = await self._source_available(
                    session, revision.config, revision.source_snapshot
                )
                if not review_view.source_available:
                    review_view.validation_passed = False
                    review_view.conclusion = "source_unavailable"
        latest = {s.question_id: s for s in view.submissions}
        rows: list[ReportQuestion] = []
        topics: dict[str, TopicReport] = {}
        scores: list[tuple[float, float]] = []
        graded_count = 0
        for question in view.questions:
            sub = latest.get(question.question_id)
            grade = sub.grades[-1] if sub and sub.grades else None
            status = grade.level if grade else "ungraded" if sub else "unsubmitted"
            if grade:
                graded_count += 1
                if grade.score is not None and grade.max_score is not None:
                    scores.append((grade.score, grade.max_score))
            rows.append(
                ReportQuestion(
                    question_id=question.question_id,
                    topics=question.topics,
                    submission=sub,
                    status=status,
                )
            )
            for name in question.topics:
                topic = topics.setdefault(name, TopicReport(topic=name))
                setattr(topic, status, getattr(topic, status) + 1)
                if grade:
                    topic.error_reasons.extend(grade.error_reasons)
                    topic.suggestions.extend(grade.suggestions)
                # This per-attempt report does not infer long-term mastery.
                topic.insufficient_sample = (topic.correct + topic.partial + topic.incorrect) < 3
        target = PracticeConfig.model_validate(revision.config).learning_target
        if target:
            from xuemian_ai.learning_assets.policy import (
                concept_key,
                fingerprint,
                review_conclusion,
            )

            concept = concept_key(str(revision.effective_context["learning_target"]["concept"]))
            related = [
                q
                for q in view.questions
                if len(q.topics) == 1 and concept_key(q.topics[0]) == concept
            ]
            submitted = graded = correct = low = 0
            refs = []
            for question in related:
                sub = latest.get(question.question_id)
                grade = sub.grades[-1] if sub and sub.grades else None
                refs.append(
                    {
                        "question": str(question.question_id),
                        "submission": str(sub.submission_id) if sub else None,
                        **({"grade": str(grade.id) if grade else None} if sub else {}),
                    }
                )
                submitted += int(sub is not None)
                graded += int(grade is not None)
                correct += int(grade is not None and grade.level == "correct")
                low += int(
                    grade is not None
                    and question.type in {"short_answer", "code_text"}
                    and (grade.confidence or 0) < 0.7
                )
            available = view.source_available
            passed, conclusion = review_conclusion(
                len(related), submitted, graded, correct, low, view.status == "completed", available
            )
            current_digest = fingerprint(
                {"refs": refs, "completed": view.status, "source_available": available}
            )
            review_view = ReportLearningReview(
                version=review.version
                if review and review.input_digest == current_digest
                else None,
                total_related=len(related),
                submitted_count=submitted,
                graded_count=graded,
                correct_count=correct,
                low_confidence_count=low,
                validation_passed=passed,
                source_available=available,
                conclusion=conclusion,
            )
        aggregate = bool(view.questions) and len(scores) == len(view.questions)
        return ReportView(
            attempt_id=view.id,
            status=view.status,
            total_questions=len(view.questions),
            submitted_count=len(latest),
            graded_count=graded_count,
            questions=rows,
            topics=list(topics.values()),
            learning_target=PracticeConfig.model_validate(revision.config).learning_target,
            learning_assets=assets,
            learning_review=review_view,
            score=sum(s[0] for s in scores) if aggregate else None,
            max_score=sum(s[1] for s in scores) if aggregate else None,
            source_mode=revision.config.get("source_mode", "general"),
        )

    async def feedback(self, body: FeedbackRequest) -> FeedbackView:
        async with self.sessions.begin() as session:
            if body.grade_id:
                grade = await session.scalar(
                    select(PracticeGrade).where(
                        PracticeGrade.id == body.grade_id, PracticeGrade.owner_user_id == self.owner
                    )
                )
                if not grade:
                    raise NotFoundError(error_key="PRACTICE_NOT_FOUND")
                await self._submission(session, grade.submission_id)
                key = f"grade:{body.grade_id}"
            else:
                rev = await session.scalar(
                    select(PracticeRevision).where(
                        PracticeRevision.id == body.revision_id,
                        PracticeRevision.owner_user_id == self.owner,
                    )
                )
                if not rev:
                    raise NotFoundError(error_key="PRACTICE_NOT_FOUND")
                await self._set(session, rev.set_id, True)
                assert body.question_id
                self._question(rev, body.question_id)
                key = f"question:{body.revision_id}:{body.question_id}"
            await session.execute(
                select(func.pg_advisory_xact_lock(int(digest([str(self.owner), key])[:15], 16)))
            )
            feedback = await session.scalar(
                select(PracticeFeedback).where(
                    PracticeFeedback.owner_user_id == self.owner, PracticeFeedback.target_key == key
                )
            )
            if feedback:
                feedback.feedback = body.feedback
            else:
                feedback = PracticeFeedback(
                    owner_user_id=self.owner, target_key=key, **body.model_dump()
                )
                session.add(feedback)
            await session.flush()
            return FeedbackView(id=feedback.id, **body.model_dump())

    async def _run(self, session: AsyncSession, run_id: UUID, lock: bool = False) -> PracticeRun:
        if lock:
            from xuemian_ai.learning_assets.service import owner_lock

            await owner_lock(session, self.owner)
        query = select(PracticeRun).where(
            PracticeRun.id == run_id, PracticeRun.owner_user_id == self.owner
        )
        run = await session.scalar(
            query.with_for_update().execution_options(populate_existing=True) if lock else query
        )
        if not run:
            raise NotFoundError(error_key="PRACTICE_NOT_FOUND")
        await self._set(session, run.set_id)
        return run

    async def get_run(self, run_id: UUID) -> RunView:
        async with self.sessions() as session:
            return run_view(await self._run(session, run_id))

    async def lookup_run(
        self, request_key: UUID, operation: str | None = None, set_id: UUID | None = None
    ) -> RunView:
        async with self.sessions() as session:
            query = select(PracticeRun).where(
                PracticeRun.owner_user_id == self.owner, PracticeRun.request_key == request_key
            )
            if operation:
                query = query.where(PracticeRun.operation == operation)
            if set_id:
                query = query.where(PracticeRun.set_id == set_id)
            run = await session.scalar(query)
            if not run:
                raise NotFoundError(error_key="PRACTICE_NOT_FOUND")
            await self._set(session, run.set_id)
            return run_view(run)

    async def cancel(self, run_id: UUID) -> RunView:
        async with self.sessions.begin() as session:
            run = await self._run(session, run_id, True)
            if run.status == "pending":
                run.status, run.stage, run.ended_at = "cancelled", "cancelled", datetime.now(UTC)
            elif run.status == "processing":
                run.status = "cancel_requested"
            elif run.status != "cancel_requested":
                raise conflict("PRACTICE_RUN_TERMINAL")
            return run_view(run)

    async def retry(self, run_id: UUID, body: RetryRequest) -> RunView:
        async with self.sessions.begin() as session:
            original = await self._run(session, run_id)
            obj = await self._set(session, original.set_id, True)
            run = await self._run(session, run_id, True)
            if run.request_key != body.request_key or run.input_digest != body.input_digest:
                raise conflict("PRACTICE_KEY_CONFLICT")
            if run.status != "failed":
                raise conflict(
                    "PRACTICE_RUN_PROCESSING"
                    if run.status in ACTIVE_RUNS
                    else "PRACTICE_RUN_TERMINAL"
                )
            if not run.retryable:
                raise conflict("PRACTICE_RETRY_UNAVAILABLE")
            await self._assert_sources(
                session, run.input_snapshot["config"], run.input_snapshot["source_snapshot"]
            )
            if run.operation in ("plan", "generate", "regenerate"):
                await self._assert_learning_target(
                    session, run.input_snapshot["config"], run.input_snapshot["effective_context"]
                )
                version_check(obj.version, int(run.input_snapshot["expected_version"]))
            elif run.submission_id:
                sub = await self._submission(session, run.submission_id)
                attempt = await self._attempt(session, sub.attempt_id)
                if run.operation == "grade":
                    self._active(attempt)
            run.status, run.stage, run.error_key = "pending", "waiting", None
            run.lease_token, run.lease_expires_at, run.ended_at = None, None, None
            run.retryable = False
            return run_view(run)

    async def claim_run(self, worker_id: str, lease_seconds: int = 30) -> PracticeRun | None:
        async with self.sessions.begin() as session:
            run = await session.scalar(
                select(PracticeRun)
                .where(PracticeRun.status == "pending")
                .order_by(PracticeRun.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not run:
                return None
            now = datetime.now(UTC)
            run.status, run.stage, run.lease_owner, run.lease_token = (
                "processing",
                "resolving",
                worker_id,
                uuid4(),
            )
            run.lease_expires_at, run.started_at = now + timedelta(seconds=lease_seconds), now
            run.attempt_count += 1
            await session.flush()
            return run

    async def heartbeat(
        self, run_id: UUID, token: UUID, lease_seconds: int = 30, stage: str | None = None
    ) -> bool:
        async with self.sessions.begin() as session:
            initial = await session.get(PracticeRun, run_id)
            if initial is None:
                return False
            from xuemian_ai.learning_assets.service import owner_lock

            await owner_lock(session, initial.owner_user_id)
            run = await session.scalar(
                select(PracticeRun)
                .where(PracticeRun.id == run_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            now = datetime.now(UTC)
            if (
                not run
                or run.lease_token != token
                or run.status != "processing"
                or not run.lease_expires_at
                or run.lease_expires_at <= now
            ):
                return False
            domain = PracticeService(self.sessions, run.owner_user_id, self.settings)
            obj = await domain._set(session, run.set_id)
            user = await session.scalar(
                select(User).where(
                    User.id == run.owner_user_id, User.status == "active", User.deleted_at.is_(None)
                )
            )
            if not user:
                raise NotFoundError(error_key="PRACTICE_NOT_FOUND")
            await domain._assert_sources(
                session, run.input_snapshot["config"], run.input_snapshot["source_snapshot"]
            )
            if run.operation in ("plan", "generate", "regenerate"):
                await domain._assert_learning_target(
                    session, run.input_snapshot["config"], run.input_snapshot["effective_context"]
                )
                version_check(obj.version, int(run.input_snapshot["expected_version"]))
            run.lease_expires_at = now + timedelta(seconds=lease_seconds)
            if stage:
                run.stage = stage
            return True

    async def expire_runs(self) -> int:
        async with self.sessions.begin() as session:
            now = datetime.now(UTC)
            runs = (
                await session.scalars(
                    select(PracticeRun)
                    .where(
                        PracticeRun.status.in_(("processing", "cancel_requested")),
                        PracticeRun.lease_expires_at <= now,
                    )
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for run in runs:
                run.status = "cancelled" if run.status == "cancel_requested" else "failed"
                run.stage, run.error_key, run.ended_at = run.status, "PRACTICE_RUN_TIMEOUT", now
                run.retryable = run.status == "failed"
                run.lease_token = None
            return len(runs)

    async def fail_run(
        self, run_id: UUID, token: UUID, error_key: str, retryable: bool = False
    ) -> bool:
        async with self.sessions.begin() as session:
            run = await session.scalar(
                select(PracticeRun)
                .where(PracticeRun.id == run_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if (
                not run
                or run.lease_token != token
                or run.status not in ("processing", "cancel_requested")
            ):
                return False
            run.status = "cancelled" if run.status == "cancel_requested" else "failed"
            run.stage, run.error_key, run.retryable, run.ended_at = (
                run.status,
                error_key,
                run.status == "failed"
                and error_key
                not in {
                    "PRACTICE_SOURCE_CHANGED",
                    "LEARNING_ASSET_SOURCE_CHANGED",
                    "LEARNING_ASSET_NOT_FOUND",
                    "LEARNING_ASSET_VERSION_CONFLICT",
                    "LEARNING_TARGET_MISMATCH",
                    "PRACTICE_VERSION_CONFLICT",
                    "PRACTICE_PLAN_STALE",
                    "PRACTICE_NOT_FOUND",
                    "PRACTICE_EVIDENCE_INSUFFICIENT",
                    "PRACTICE_CONFIG_INVALID",
                },
                datetime.now(UTC),
            )
            run.lease_token = None
            return True

    async def publish_run(
        self,
        run_id: UUID,
        token: UUID,
        result: dict[str, Any],
        manifest: dict[str, Any] | None = None,
    ) -> bool:
        async with self.sessions.begin() as session:
            initial = await session.get(PracticeRun, run_id)
            if not initial:
                return False
            # Lock publication target before execution record, matching edit/retry transactions.
            owner = initial.owner_user_id
            from xuemian_ai.learning_assets.service import owner_lock

            await owner_lock(session, owner)
            obj = await session.scalar(
                select(PracticeSet).where(PracticeSet.id == initial.set_id).with_for_update()
            )
            run = await session.scalar(
                select(PracticeRun)
                .where(PracticeRun.id == run_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            now = datetime.now(UTC)
            if (
                not run
                or run.lease_token != token
                or run.status not in ("processing", "cancel_requested")
                or not run.lease_expires_at
                or run.lease_expires_at <= now
            ):
                return False
            if run.status == "cancel_requested":
                run.status, run.stage, run.ended_at, run.lease_token = (
                    "cancelled",
                    "cancelled",
                    now,
                    None,
                )
                return False
            user = await session.scalar(
                select(User).where(
                    User.id == owner, User.status == "active", User.deleted_at.is_(None)
                )
            )
            if not obj or obj.deleted_at or obj.owner_user_id != owner or not user:
                run.status, run.stage, run.error_key, run.ended_at, run.lease_token = (
                    "failed",
                    "failed",
                    "PRACTICE_NOT_FOUND",
                    now,
                    None,
                )
                run.retryable = False
                return False
            domain = PracticeService(self.sessions, owner, self.settings)
            snapshot = run.input_snapshot
            await domain._assert_sources(session, snapshot["config"], snapshot["source_snapshot"])
            if run.operation in ("plan", "generate", "regenerate"):
                await domain._assert_learning_target(
                    session, snapshot["config"], snapshot["effective_context"]
                )
                version_check(obj.version, int(snapshot["expected_version"]))
            if run.operation == "plan":
                original = PracticeConfig.model_validate(snapshot["config"])
                context = snapshot["effective_context"]
                recommended_input = dict(result["recommended_config"])
                if "learning_target" in recommended_input and recommended_input[
                    "learning_target"
                ] != snapshot["config"].get("learning_target"):
                    raise ValidationAppError(
                        "建议不能改变学习目标", error_key="PRACTICE_GENERATION_INVALID"
                    )
                if original.learning_target:
                    recommended_input["learning_target"] = original.learning_target.model_dump(
                        mode="json"
                    )
                for field in PROFILE_FIELDS:
                    if (
                        field not in recommended_input
                        and context.get("sources", {}).get(field) == "explicit"
                    ):
                        recommended_input[field] = context.get("values", {}).get(field)
                recommended = PracticeConfig.model_validate(recommended_input)
                if (original.source_mode, original.knowledge_base_id, original.file_ids) != (
                    recommended.source_mode,
                    recommended.knowledge_base_id,
                    recommended.file_ids,
                ):
                    raise ValidationAppError(
                        "建议不能改变来源", error_key="PRACTICE_GENERATION_INVALID"
                    )
                context = snapshot["effective_context"]
                from xuemian_ai.practice.context import ensure_general_topic, resolve_context

                frozen_profile = dict(context.get("values", {}))
                frozen_profile["version"] = context.get("profile_version")
                recommendation_overrides = {
                    field: getattr(recommended, field)
                    for field in PROFILE_FIELDS
                    if field in recommended.model_fields_set
                }
                recommended_context = resolve_context(recommendation_overrides, frozen_profile)
                if original.learning_target:
                    recommended_context["learning_target"] = context["learning_target"]
                    await domain._assert_learning_target(
                        session, config_dump(recommended), recommended_context
                    )
                ensure_general_topic(recommended.model_dump(mode="json"), recommended_context)
                candidates = {
                    "original": PlanCandidate(
                        config=original,
                        summary=str(result["summary"]),
                        config_digest=digest(original.model_dump(mode="json")),
                        effective_context=context,
                    ).model_dump(mode="json"),
                    "recommended": PlanCandidate(
                        config=recommended,
                        summary=str(result.get("recommendation_summary", result["summary"])),
                        config_digest=digest(recommended.model_dump(mode="json")),
                        effective_context=recommended_context,
                    ).model_dump(mode="json"),
                }
                number = (
                    await session.scalar(
                        select(func.max(PracticePlan.version)).where(PracticePlan.set_id == obj.id)
                    )
                    or 0
                ) + 1
                plan = PracticePlan(
                    id=uuid4(),
                    owner_user_id=owner,
                    set_id=obj.id,
                    version=number,
                    base_set_version=obj.version,
                    candidates=candidates,
                    suggestions=result.get("suggestions", []),
                    input_digest=run.input_digest,
                    run_id=run.id,
                )
                session.add(plan)
                ref = ResultRef(type="plan", id=plan.id, version=number)
            elif run.operation in ("generate", "regenerate"):
                from xuemian_ai.practice.generation import validate_question_snapshots

                config = snapshot.get("revision_config", snapshot["config"])
                # Worker returns the complete group, including a single-question replacement.
                validation_config = None if run.operation == "regenerate" else snapshot["config"]
                questions = validate_question_snapshots(result["questions"], validation_config)
                if run.operation == "regenerate":
                    old = snapshot["questions"]
                    if len(questions) != len(old):
                        raise ValidationAppError(
                            "重新生成数量不匹配", error_key="PRACTICE_GENERATION_INVALID"
                        )
                    if snapshot.get("question_id"):
                        old_by_id = {str(q["question_id"]): q for q in old}
                        for q in questions:
                            original_q = old_by_id.get(str(q["question_id"]))
                            if not original_q or (q["type"], q["difficulty"]) != (
                                original_q["type"],
                                original_q["difficulty"],
                            ):
                                raise ValidationAppError(
                                    "单题重新生成类型改变", error_key="PRACTICE_GENERATION_INVALID"
                                )
                            if (
                                str(q["question_id"]) != str(snapshot["question_id"])
                                and q != original_q
                            ):
                                raise ValidationAppError(
                                    "重新生成覆盖其他题目", error_key="PRACTICE_GENERATION_INVALID"
                                )
                rev = await domain._new_revision(
                    session,
                    obj,
                    questions,
                    config,
                    snapshot["effective_context"],
                    snapshot["source_snapshot"],
                    run.operation,
                    run,
                    manifest,
                )
                ref = ResultRef(type="revision", id=rev.id, version=rev.version)
            else:
                from xuemian_ai.practice.grading import validate_subjective_grade

                assert run.submission_id
                sub = await domain._submission(session, run.submission_id)
                attempt = await domain._attempt(session, sub.attempt_id)
                if run.operation == "grade":
                    domain._active(attempt)
                payload = validate_subjective_grade(result["grade"], sub.question, sub.answer)
                grade = await domain._save_grade(session, sub, payload, run, manifest)
                ref = ResultRef(type="grade", id=grade.id, version=grade.version)
            run.status, run.stage, run.ended_at, run.lease_token = (
                "succeeded",
                "completed",
                now,
                None,
            )
            run.result_ref, run.manifest = ref.model_dump(mode="json"), manifest or {}
            await session.flush()
            return True
