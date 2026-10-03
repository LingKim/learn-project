from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from xuemian_ai.accounts.models import User
from xuemian_ai.core.errors import ConflictError, NotFoundError, ValidationAppError
from xuemian_ai.core.responses import PageResponse, page_response
from xuemian_ai.document_processing.models import DocumentProcessingVersion
from xuemian_ai.file_management.models import FileAsset, KnowledgeBaseFile
from xuemian_ai.knowledge_bases.models import KnowledgeBase
from xuemian_ai.learning_assets.models import (
    KnowledgeCardVersion,
    KnowledgeExplanation,
    KnowledgeRun,
    LearningReview,
    Weakness,
    WeaknessEvent,
    WeaknessEvidence,
)
from xuemian_ai.learning_assets.policy import concept_key, fingerprint, scope_key
from xuemian_ai.learning_assets.schemas import (
    EvidenceView,
    ExplanationAccepted,
    ExplanationConfig,
    ExplanationCreate,
    ExplanationDetail,
    ExplanationRegenerate,
    ExplanationView,
    KnowledgeCardPayload,
    KnowledgeCardView,
    KnowledgeRunView,
    LearningReviewView,
    MasteryRequest,
    SourceConfig,
    WeaknessCreate,
    WeaknessDetail,
    WeaknessEventView,
    WeaknessPatch,
    WeaknessView,
)
from xuemian_ai.practice.models import (
    PracticeAttempt,
    PracticeRevision,
    PracticeSet,
    PracticeSubmission,
)
from xuemian_ai.profiles.models import UserProfile

ACTIVE_RUNS = ("pending", "processing", "cancel_requested")


def conflict(key: str = "LEARNING_ASSET_VERSION_CONFLICT") -> ConflictError:
    return ConflictError("学习资产状态已变化，请重新读取后操作", error_key=key)


def check_version(actual: int, expected: int) -> None:
    if actual != expected:
        raise conflict()


async def owner_lock(session: AsyncSession, owner: UUID) -> None:
    # Serialize all mutations/projections for one owner, while workers still claim independently.
    key = int(fingerprint(str(owner))[:15], 16)
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


async def sources_current(
    session: AsyncSession, owner: UUID, config: dict[str, Any]
) -> list[dict[str, Any]]:
    parsed = SourceConfig.model_validate(
        {
            key: config.get(
                key, [] if key == "file_ids" else "general" if key == "source_mode" else None
            )
            for key in SourceConfig.model_fields
        }
    )
    if parsed.source_mode == "general":
        return []
    kb = await session.scalar(
        select(KnowledgeBase)
        .where(
            KnowledgeBase.id == parsed.knowledge_base_id,
            KnowledgeBase.owner_user_id == owner,
            KnowledgeBase.deleted_at.is_(None),
        )
        .with_for_update(read=True)
    )
    if kb is None:
        raise NotFoundError(error_key="LEARNING_ASSET_NOT_FOUND")
    query = (
        select(KnowledgeBaseFile, DocumentProcessingVersion)
        .join(FileAsset, KnowledgeBaseFile.file_asset_id == FileAsset.id)
        .join(DocumentProcessingVersion, DocumentProcessingVersion.file_asset_id == FileAsset.id)
        .where(
            KnowledgeBaseFile.knowledge_base_id == kb.id,
            KnowledgeBaseFile.deleted_at.is_(None),
            FileAsset.deleted_at.is_(None),
            FileAsset.owner_user_id == owner,
            FileAsset.validation_status == "available",
            DocumentProcessingVersion.status == "active",
            DocumentProcessingVersion.user_id == owner,
        )
    )
    if parsed.file_ids:
        query = query.where(KnowledgeBaseFile.id.in_(parsed.file_ids))
    rows = (
        await session.execute(
            query.with_for_update(
                read=True, of=(KnowledgeBaseFile, FileAsset, DocumentProcessingVersion)
            )
        )
    ).all()
    if parsed.file_ids and set(parsed.file_ids) != {file.id for file, _ in rows}:
        raise conflict("LEARNING_ASSET_SOURCE_CHANGED")
    if not rows:
        raise ValidationAppError(
            "资料没有可用解析版本", error_key="KNOWLEDGE_EVIDENCE_INSUFFICIENT"
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


async def sources_available(
    session: AsyncSession, owner: UUID, config: dict[str, Any], snapshot: list[dict[str, Any]]
) -> bool:
    if config.get("source_mode", "general") == "general":
        return True
    if not snapshot:
        return False
    fixed = {**config, "file_ids": [item["file_id"] for item in snapshot]}
    try:
        current = await sources_current(session, owner, fixed)
        fields = (
            "file_id",
            "file_asset_id",
            "processing_version_id",
            "knowledge_base_id",
            "resource_version",
        )
        return {tuple(str(item.get(key)) for key in fields) for item in current} == {
            tuple(str(item.get(key)) for key in fields) for item in snapshot
        }
    except (ConflictError, NotFoundError, ValidationAppError):
        return False


def run_view(run: KnowledgeRun) -> KnowledgeRunView:
    return KnowledgeRunView.model_validate(
        {key: getattr(run, key) for key in KnowledgeRunView.model_fields}
    )


def event(
    session: AsyncSession,
    obj: Weakness,
    name: str,
    actor: UUID | None,
    payload: dict[str, Any] | None = None,
    request_key: UUID | None = None,
) -> None:
    session.add(
        WeaknessEvent(
            owner_user_id=obj.owner_user_id,
            weakness_id=obj.id,
            event_type=name,
            version=obj.version,
            actor_user_id=actor,
            request_key=request_key,
            payload=payload or {},
        )
    )


async def evidence_available(
    session: AsyncSession, owner: UUID, obj: Weakness, evidence: WeaknessEvidence
) -> bool:
    if evidence.kind == "manual":
        return await sources_available(session, owner, obj.source_config, obj.source_snapshot)
    if evidence.attempt_id is None or evidence.revision_id is None:
        return False
    revision = await session.scalar(
        select(PracticeRevision).where(
            PracticeRevision.id == evidence.revision_id, PracticeRevision.owner_user_id == owner
        )
    )
    if revision is None or not await sources_available(
        session, owner, revision.config, revision.source_snapshot
    ):
        return False
    source = await session.scalar(
        select(PracticeSet)
        .join(PracticeAttempt, PracticeAttempt.set_id == PracticeSet.id)
        .where(
            PracticeAttempt.id == evidence.attempt_id,
            PracticeAttempt.owner_user_id == owner,
            PracticeSet.owner_user_id == owner,
            PracticeSet.deleted_at.is_(None),
        )
    )
    return source is not None


async def resolve_learning_target(
    session: AsyncSession, owner: UUID, target_dump: dict[str, Any], config_dump: dict[str, Any]
) -> dict[str, Any]:
    domain = LearningAssetService(cast(Any, None), owner)
    kind = target_dump.get("kind")
    context: dict[str, Any] = {}
    if kind == "weakness":
        obj = await domain._weakness(session, UUID(str(target_dump["id"])))
        check_version(obj.version, int(target_dump["version"]))
        if obj.decision != "confirmed":
            raise conflict("LEARNING_ASSET_SOURCE_CHANGED")
        source, snapshot, title = obj.source_config, obj.source_snapshot, obj.title
        if obj.explanation_id:
            explanation_context = await session.scalar(
                select(KnowledgeExplanation).where(
                    KnowledgeExplanation.id == obj.explanation_id,
                    KnowledgeExplanation.owner_user_id == owner,
                    KnowledgeExplanation.deleted_at.is_(None),
                )
            )
            if explanation_context:
                context = dict(explanation_context.effective_context.get("values", {}))
        evidence = list(
            await session.scalars(
                select(WeaknessEvidence).where(
                    WeaknessEvidence.weakness_id == obj.id,
                    WeaknessEvidence.owner_user_id == owner,
                    WeaknessEvidence.superseded.is_(False),
                    WeaknessEvidence.ignored.is_(False),
                )
            )
        )
        if not any([await evidence_available(session, owner, obj, item) for item in evidence]):
            raise conflict("LEARNING_ASSET_SOURCE_CHANGED")
    elif kind == "explanation":
        explanation = await domain._explanation(session, UUID(str(target_dump["id"])))
        card = await session.scalar(
            select(KnowledgeCardVersion).where(
                KnowledgeCardVersion.explanation_id == explanation.id,
                KnowledgeCardVersion.version == int(target_dump["card_version"]),
                KnowledgeCardVersion.owner_user_id == owner,
            )
        )
        if card is None:
            raise NotFoundError(error_key="LEARNING_ASSET_NOT_FOUND")
        source, snapshot, title = card.config, card.source_snapshot, str(card.config["topic"])
        allowed_fields = (
            "target_job",
            "experience_months",
            "target_level",
            "target_skills",
            "focus_topics",
            "learning_goal",
            "preferred_language",
        )
        context = {key: card.config[key] for key in allowed_fields if key in card.config}
    else:
        raise ValidationAppError("学习目标不合法", error_key="LEARNING_TARGET_MISMATCH")
    if not await sources_available(session, owner, source, snapshot):
        raise conflict("LEARNING_ASSET_SOURCE_CHANGED")
    if concept_key(str(config_dump.get("topic", ""))) != concept_key(title) or scope_key(
        config_dump
    ) != scope_key(source):
        raise ValidationAppError(
            "练习主题或资料范围与目标不一致，请调整配置或取消关联",
            error_key="LEARNING_TARGET_MISMATCH",
        )
    return {
        **target_dump,
        "topic": title,
        "concept": title,
        "source_mode": source.get("source_mode", "general"),
        "knowledge_base_id": source.get("knowledge_base_id"),
        "file_ids": source.get("file_ids", []),
        "source_config": {key: source.get(key) for key in SourceConfig.model_fields},
        "source_snapshot": snapshot,
        "context": context,
    }


class LearningAssetService:
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], owner_user_id: UUID, settings: Any = None
    ) -> None:
        self.sessions, self.owner, self.settings = sessions, owner_user_id, settings

    async def _weakness(
        self, session: AsyncSession, object_id: UUID, lock: bool = False
    ) -> Weakness:
        query = select(Weakness).where(
            Weakness.id == object_id,
            Weakness.owner_user_id == self.owner,
            Weakness.deleted_at.is_(None),
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        obj = await session.scalar(query)
        if obj is None:
            raise NotFoundError(error_key="LEARNING_ASSET_NOT_FOUND")
        return obj

    async def _explanation(
        self, session: AsyncSession, object_id: UUID, lock: bool = False
    ) -> KnowledgeExplanation:
        query = select(KnowledgeExplanation).where(
            KnowledgeExplanation.id == object_id,
            KnowledgeExplanation.owner_user_id == self.owner,
            KnowledgeExplanation.deleted_at.is_(None),
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        obj = await session.scalar(query)
        if obj is None:
            raise NotFoundError(error_key="LEARNING_ASSET_NOT_FOUND")
        return obj

    async def _run(self, session: AsyncSession, run_id: UUID, lock: bool = False) -> KnowledgeRun:
        query = select(KnowledgeRun).where(
            KnowledgeRun.id == run_id, KnowledgeRun.owner_user_id == self.owner
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        obj = await session.scalar(query)
        if obj is None:
            raise NotFoundError(error_key="LEARNING_ASSET_NOT_FOUND")
        return obj

    async def _latest_run(
        self, session: AsyncSession, explanation_id: UUID | None
    ) -> KnowledgeRunView | None:
        if explanation_id is None:
            return None
        run = await session.scalar(
            select(KnowledgeRun)
            .where(
                KnowledgeRun.explanation_id == explanation_id,
                KnowledgeRun.owner_user_id == self.owner,
            )
            .order_by(KnowledgeRun.created_at.desc(), KnowledgeRun.id.desc())
            .limit(1)
        )
        return run_view(run) if run else None

    async def _weakness_view(self, session: AsyncSession, obj: Weakness) -> WeaknessView:
        await session.flush()
        await session.refresh(obj, ["updated_at"])
        explanation = (
            await session.scalar(
                select(KnowledgeExplanation).where(
                    KnowledgeExplanation.id == obj.explanation_id,
                    KnowledgeExplanation.owner_user_id == self.owner,
                    KnowledgeExplanation.deleted_at.is_(None),
                )
            )
            if obj.explanation_id
            else None
        )
        evidence = list(
            await session.scalars(
                select(WeaknessEvidence).where(
                    WeaknessEvidence.weakness_id == obj.id,
                    WeaknessEvidence.owner_user_id == self.owner,
                )
            )
        )
        available_count = len(
            [
                item
                for item in evidence
                if not item.superseded
                and not item.ignored
                and await evidence_available(session, self.owner, obj, item)
            ]
        )
        return WeaknessView(
            evidence_count=len(evidence),
            available_evidence_count=available_count,
            id=obj.id,
            title=obj.title,
            domain=obj.domain,
            tags=obj.tags,
            severity=cast(Any, obj.severity),
            decision=cast(Any, obj.decision),
            mastery_state=cast(Any, obj.mastery_state),
            version=obj.version,
            evidence_sufficient=obj.evidence_sufficient,
            policy_version=obj.policy_version,
            source_available=any(
                [
                    await evidence_available(session, self.owner, obj, item)
                    for item in evidence
                    if not item.superseded
                ]
            ),
            explanation_id=explanation.id if explanation else None,
            active_card_version=explanation.active_card_version if explanation else None,
            run=await self._latest_run(session, explanation.id if explanation else None),
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            **obj.source_config,
        )

    async def _explanation_view(
        self, session: AsyncSession, obj: KnowledgeExplanation
    ) -> ExplanationView:
        await session.flush()
        await session.refresh(obj, ["updated_at"])
        return ExplanationView(
            id=obj.id,
            weakness_id=obj.weakness_id,
            topic=obj.topic,
            version=obj.version,
            config=ExplanationConfig.model_validate(obj.config),
            active_card_version=obj.active_card_version,
            source_available=await sources_available(
                session, self.owner, obj.config, obj.source_snapshot
            ),
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

    async def _card_view(
        self, session: AsyncSession, card: KnowledgeCardVersion
    ) -> KnowledgeCardView:
        # Saved business content remains, but references never include stale source text.
        available = await sources_available(session, self.owner, card.config, card.source_snapshot)
        return KnowledgeCardView(
            config=ExplanationConfig.model_validate(card.config),
            id=card.id,
            explanation_id=card.explanation_id,
            version=card.version,
            parent_version=card.parent_version,
            foundation=card.config["foundation"],
            depth=card.config["depth"],
            preferred_language=card.config.get("preferred_language") or "zh-CN",
            source_available=available,
            created_at=card.created_at,
            **card.payload,
        )

    async def _effective(self, session: AsyncSession, config: ExplanationConfig) -> dict[str, Any]:
        from xuemian_ai.practice.context import resolve_context

        fields = (
            "target_job",
            "experience_months",
            "target_level",
            "target_skills",
            "focus_topics",
            "learning_goal",
            "preferred_language",
        )
        profile = await session.scalar(select(UserProfile).where(UserProfile.user_id == self.owner))
        defaults = {key: getattr(profile, key) for key in fields} if profile else None
        return resolve_context(
            {key: getattr(config, key) for key in fields if key in config.model_fields_set},
            defaults,
        )

    async def _enqueue(
        self,
        session: AsyncSession,
        obj: KnowledgeExplanation,
        key: UUID,
        operation: str,
        fingerprint_input: str | None = None,
    ) -> KnowledgeRun:
        if await session.scalar(
            select(KnowledgeRun.id).where(
                KnowledgeRun.explanation_id == obj.id, KnowledgeRun.status.in_(ACTIVE_RUNS)
            )
        ):
            raise conflict("KNOWLEDGE_RUN_CONFLICT")
        snapshot: dict[str, Any] = {
            "config": obj.config,
            "effective_context": obj.effective_context,
            "source_snapshot": obj.source_snapshot,
            "weakness_id": str(obj.weakness_id) if obj.weakness_id else None,
        }
        if obj.weakness_id:
            weakness = await self._weakness(session, obj.weakness_id)
            snapshot["weakness_version"] = weakness.version
        run = KnowledgeRun(
            owner_user_id=self.owner,
            explanation_id=obj.id,
            expected_version=obj.version,
            operation=operation,
            request_key=key,
            input_digest=fingerprint_input or fingerprint(snapshot),
            input_snapshot=snapshot,
        )
        session.add(run)
        await session.flush()
        return run

    async def _first_card(self, session: AsyncSession, obj: Weakness) -> KnowledgeRun | None:
        if obj.explanation_id:
            return None
        key = uuid5(NAMESPACE_URL, f"xuemian:weakness:{obj.id}:first-card")
        config = ExplanationConfig(topic=obj.title, **obj.source_config)
        effective = await self._effective(session, config)
        data = config.model_dump(mode="json")
        data["preferred_language"] = (
            effective.get("values", {}).get("preferred_language") or "zh-CN"
        )
        explanation = KnowledgeExplanation(
            owner_user_id=self.owner,
            weakness_id=obj.id,
            topic=obj.title,
            config=data,
            effective_context=effective,
            source_snapshot=obj.source_snapshot,
            request_key=key,
            input_digest=fingerprint(data),
            created_by=self.owner,
            updated_by=self.owner,
        )
        session.add(explanation)
        await session.flush()
        obj.explanation_id = explanation.id
        return await self._enqueue(session, explanation, key, "generate")

    async def create(self, body: WeaknessCreate) -> WeaknessView:
        data = body.model_dump(mode="json", exclude={"request_key"})
        fp = fingerprint(data)
        async with self.sessions.begin() as session:
            await owner_lock(session, self.owner)
            existing = await session.scalar(
                select(Weakness).where(
                    Weakness.owner_user_id == self.owner, Weakness.request_key == body.request_key
                )
            )
            if existing:
                if existing.input_digest != fp:
                    raise conflict("LEARNING_ASSET_KEY_CONFLICT")
                if existing.deleted_at:
                    raise NotFoundError(error_key="LEARNING_ASSET_NOT_FOUND")
                return await self._weakness_view(session, existing)
            source = SourceConfig.model_validate(
                {key: data[key] for key in SourceConfig.model_fields}
            ).model_dump(mode="json")
            snapshot = await sources_current(session, self.owner, source)
            duplicate = await session.scalar(
                select(Weakness).where(
                    Weakness.owner_user_id == self.owner,
                    Weakness.source_scope_key == scope_key(source),
                    Weakness.concept_key == concept_key(body.title),
                    Weakness.deleted_at.is_(None),
                )
            )
            if duplicate:
                raise conflict("LEARNING_ASSET_DUPLICATE")
            obj = Weakness(
                owner_user_id=self.owner,
                title=body.title.strip(),
                concept_key=concept_key(body.title),
                source_scope_key=scope_key(source),
                source_config=source,
                source_snapshot=snapshot,
                domain=body.domain,
                tags=body.tags,
                severity=body.severity,
                decision="confirmed",
                evidence_sufficient=True,
                request_key=body.request_key,
                input_digest=fp,
                created_by=self.owner,
                updated_by=self.owner,
                last_user_action_at=datetime.now(UTC),
            )
            session.add(obj)
            await session.flush()
            session.add(
                WeaknessEvidence(
                    owner_user_id=self.owner,
                    weakness_id=obj.id,
                    kind="manual",
                    source_key="manual:" + str(body.request_key),
                    detail={
                        "declaration": "user_learning_goal",
                        "title": obj.title,
                        "source_config": source,
                        "source_snapshot": snapshot,
                        "confirmed_by": str(self.owner),
                    },
                )
            )
            event(session, obj, "manual_created", self.owner, {"source": "user_declared"})
            await self._first_card(session, obj)
            await session.flush()
            return await self._weakness_view(session, obj)

    async def list_weaknesses(
        self,
        page: int = 1,
        page_size: int = 20,
        query: str | None = None,
        tags: list[str] | None = None,
        severity: str | None = None,
        mastery_state: str | None = None,
        decision: str = "confirmed",
        domain: str | None = None,
        source_mode: str | None = None,
    ) -> PageResponse[WeaknessView]:
        async with self.sessions() as session:
            conditions = [
                Weakness.owner_user_id == self.owner,
                Weakness.deleted_at.is_(None),
                Weakness.decision == decision,
            ]
            if query:
                conditions.append(
                    Weakness.title.ilike("%" + query.replace("%", "\\%").replace("_", "\\_") + "%")
                )
            if tags:
                conditions.append(Weakness.tags.contains(tags))
            if domain:
                conditions.append(Weakness.domain == domain)
            if source_mode:
                conditions.append(Weakness.source_config["source_mode"].astext == source_mode)
            if severity:
                conditions.append(Weakness.severity == severity)
            if mastery_state:
                conditions.append(Weakness.mastery_state == mastery_state)
            total = (
                await session.scalar(select(func.count()).select_from(Weakness).where(*conditions))
                or 0
            )
            objects = list(
                await session.scalars(
                    select(Weakness)
                    .where(*conditions)
                    .order_by(Weakness.updated_at.desc(), Weakness.id)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            return page_response(
                [await self._weakness_view(session, obj) for obj in objects],
                page=page,
                page_size=page_size,
                total=total,
            )

    async def detail(self, object_id: UUID) -> WeaknessDetail:
        async with self.sessions() as session:
            obj = await self._weakness(session, object_id)
            view = await self._weakness_view(session, obj)
            evidence = list(
                await session.scalars(
                    select(WeaknessEvidence)
                    .where(
                        WeaknessEvidence.weakness_id == obj.id,
                        WeaknessEvidence.owner_user_id == self.owner,
                    )
                    .order_by(WeaknessEvidence.created_at.desc())
                )
            )
            evidence_views = []
            for item in evidence:
                available = await evidence_available(session, self.owner, obj, item)
                detail = dict(item.detail) if available else None
                if available and item.kind == "practice" and item.submission_id:
                    submission = await session.scalar(
                        select(PracticeSubmission).where(
                            PracticeSubmission.id == item.submission_id,
                            PracticeSubmission.owner_user_id == self.owner,
                        )
                    )
                    if submission:
                        detail = {
                            **(detail or {}),
                            "question": submission.question,
                            "answer": submission.answer,
                            "set_id": str(
                                cast(
                                    PracticeAttempt,
                                    await session.get(PracticeAttempt, submission.attempt_id),
                                ).set_id
                            ),
                        }
                evidence_views.append(
                    EvidenceView(
                        id=item.id,
                        kind=cast(Any, item.kind),
                        question_id=item.question_id,
                        attempt_id=item.attempt_id,
                        submission_id=item.submission_id,
                        grade_id=item.grade_id,
                        grade_version=item.grade_version,
                        submitted_at=item.submitted_at,
                        available=available,
                        superseded=item.superseded,
                        ignored=item.ignored,
                        detail=detail,
                        created_at=item.created_at,
                    )
                )
            events = list(
                await session.scalars(
                    select(WeaknessEvent)
                    .where(
                        WeaknessEvent.weakness_id == obj.id,
                        WeaknessEvent.owner_user_id == self.owner,
                    )
                    .order_by(WeaknessEvent.created_at.desc(), WeaknessEvent.id)
                )
            )
            card = None
            if view.explanation_id and view.active_card_version:
                stored = await session.scalar(
                    select(KnowledgeCardVersion).where(
                        KnowledgeCardVersion.explanation_id == view.explanation_id,
                        KnowledgeCardVersion.version == view.active_card_version,
                        KnowledgeCardVersion.owner_user_id == self.owner,
                    )
                )
                if stored:
                    card = await self._card_view(session, stored)
            reviews = await self._review_rows(session, obj.id, 1, 20)
            versions = (
                list(
                    await session.scalars(
                        select(KnowledgeCardVersion.version)
                        .where(
                            KnowledgeCardVersion.explanation_id == view.explanation_id,
                            KnowledgeCardVersion.owner_user_id == self.owner,
                        )
                        .order_by(KnowledgeCardVersion.version.desc())
                    )
                )
                if view.explanation_id
                else []
            )
            return WeaknessDetail(
                **view.model_dump(),
                card_versions=versions,
                evidence=evidence_views,
                events=[
                    WeaknessEventView.model_validate(
                        {key: getattr(item, key) for key in WeaknessEventView.model_fields}
                    )
                    for item in events
                ],
                card=card,
                reviews=reviews,
            )

    async def patch(self, object_id: UUID, body: WeaknessPatch) -> WeaknessView:
        async with self.sessions.begin() as session:
            await owner_lock(session, self.owner)
            obj = await self._weakness(session, object_id, True)
            check_version(obj.version, body.expected_version)
            if body.title is not None:
                duplicate = await session.scalar(
                    select(Weakness.id).where(
                        Weakness.owner_user_id == self.owner,
                        Weakness.source_scope_key == obj.source_scope_key,
                        Weakness.concept_key == concept_key(body.title),
                        Weakness.id != obj.id,
                        Weakness.deleted_at.is_(None),
                    )
                )
                if duplicate:
                    raise conflict("LEARNING_ASSET_DUPLICATE")
                obj.title, obj.concept_key = body.title.strip(), concept_key(body.title)
            for name in ("domain", "tags", "severity"):
                if name in body.model_fields_set:
                    value = getattr(body, name)
                    if name != "domain" and value is None:
                        raise ValidationAppError(
                            "标签和严重度不能清空", error_key="KNOWLEDGE_CONFIG_INVALID"
                        )
                    setattr(obj, name, value)
            obj.version += 1
            obj.updated_by, obj.last_user_action_at = self.owner, datetime.now(UTC)
            event(
                session,
                obj,
                "edited",
                self.owner,
                body.model_dump(mode="json", exclude={"expected_version"}, exclude_unset=True),
            )
            await session.flush()
            return await self._weakness_view(session, obj)

    async def decide(
        self, object_id: UUID, expected_version: int, decision: str, request_key: UUID | None = None
    ) -> WeaknessView:
        async with self.sessions.begin() as session:
            await owner_lock(session, self.owner)
            obj = await self._weakness(session, object_id, True)
            if request_key:
                prior = await session.scalar(
                    select(WeaknessEvent).where(
                        WeaknessEvent.owner_user_id == self.owner,
                        WeaknessEvent.request_key == request_key,
                    )
                )
                if prior:
                    if prior.weakness_id != obj.id or prior.event_type != "confirmed":
                        raise conflict("LEARNING_ASSET_KEY_CONFLICT")
                    return await self._weakness_view(session, obj)
            check_version(obj.version, expected_version)
            if decision == "confirmed":
                if obj.decision == "confirmed":
                    raise conflict()
                evidence = list(
                    await session.scalars(
                        select(WeaknessEvidence).where(
                            WeaknessEvidence.weakness_id == obj.id,
                            WeaknessEvidence.superseded.is_(False),
                            WeaknessEvidence.ignored.is_(False),
                        )
                    )
                )
                if not any(
                    [await evidence_available(session, self.owner, obj, item) for item in evidence]
                ):
                    raise conflict("LEARNING_ASSET_SOURCE_CHANGED")
            elif decision == "ignored" and obj.decision != "pending":
                raise conflict()
            elif decision == "revoked" and obj.decision != "confirmed":
                raise conflict()
            obj.decision, obj.version = decision, obj.version + 1
            obj.last_user_action_at, obj.updated_by = datetime.now(UTC), self.owner
            if decision in {"ignored", "revoked"}:
                evidence = list(
                    await session.scalars(
                        select(WeaknessEvidence).where(WeaknessEvidence.weakness_id == obj.id)
                    )
                )
                blocked = set(obj.blocked_question_ids)
                for item in evidence:
                    item.ignored = True
                    if item.question_id:
                        blocked.add(str(item.question_id))
                obj.blocked_question_ids = sorted(blocked)
                await self._cancel_weakness_runs(session, obj)
            event(
                session,
                obj,
                decision,
                self.owner,
                {"source": "user_confirmed"} if decision == "confirmed" else None,
                request_key,
            )
            if decision == "confirmed":
                await self._first_card(session, obj)
            await session.flush()
            return await self._weakness_view(session, obj)

    async def _cancel_weakness_runs(self, session: AsyncSession, obj: Weakness) -> None:
        if obj.explanation_id:
            runs = list(
                await session.scalars(
                    select(KnowledgeRun)
                    .where(
                        KnowledgeRun.explanation_id == obj.explanation_id,
                        KnowledgeRun.status.in_(ACTIVE_RUNS),
                    )
                    .with_for_update()
                )
            )
            for run in runs:
                run.status = "cancelled" if run.status == "pending" else "cancel_requested"
                run.stage = "cancelled" if run.status == "cancelled" else run.stage
                if run.status == "cancelled":
                    run.ended_at = datetime.now(UTC)

    async def mastery(self, object_id: UUID, body: MasteryRequest) -> WeaknessView:
        async with self.sessions.begin() as session:
            await owner_lock(session, self.owner)
            obj = await self._weakness(session, object_id, True)
            check_version(obj.version, body.expected_version)
            if obj.decision != "confirmed":
                raise conflict()
            previous = obj.mastery_state
            obj.mastery_state, obj.version = body.mastery_state, obj.version + 1
            obj.last_user_action_at, obj.updated_by = datetime.now(UTC), self.owner
            event(
                session,
                obj,
                "mastery_changed",
                self.owner,
                {"from": previous, "to": body.mastery_state, "reason": "user_explicit"},
            )
            await session.flush()
            return await self._weakness_view(session, obj)

    async def delete(self, object_id: UUID, expected_version: int) -> None:
        async with self.sessions.begin() as session:
            await owner_lock(session, self.owner)
            obj = await self._weakness(session, object_id, True)
            check_version(obj.version, expected_version)
            obj.deleted_at, obj.deleted_by = datetime.now(UTC), self.owner
            obj.version += 1
            await self._cancel_weakness_runs(session, obj)
            event(session, obj, "deleted", self.owner)

    async def _review_rows(
        self, session: AsyncSession, target_id: UUID, page: int, page_size: int
    ) -> list[LearningReviewView]:
        rows = list(
            await session.scalars(
                select(LearningReview)
                .where(
                    LearningReview.owner_user_id == self.owner,
                    LearningReview.target_id == target_id,
                )
                .order_by(LearningReview.created_at.desc(), LearningReview.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        result = []
        for row in rows:
            source = await session.scalar(
                select(PracticeSet).where(
                    PracticeSet.id == row.set_id,
                    PracticeSet.owner_user_id == self.owner,
                    PracticeSet.deleted_at.is_(None),
                )
            )
            available = bool(source) and await sources_available(
                session,
                self.owner,
                row.target_snapshot.get("source_config", {}),
                row.target_snapshot.get("source_snapshot", []),
            )
            data = {key: getattr(row, key) for key in LearningReviewView.model_fields}
            data["source_available"] = available
            if not available:
                data["validation_passed"] = False
                data["conclusion"] = "source_unavailable"
            result.append(LearningReviewView.model_validate(data))
        return result

    async def reviews(
        self, object_id: UUID, page: int, page_size: int
    ) -> PageResponse[LearningReviewView]:
        async with self.sessions() as session:
            await self._weakness(session, object_id)
            total = (
                await session.scalar(
                    select(func.count())
                    .select_from(LearningReview)
                    .where(
                        LearningReview.owner_user_id == self.owner,
                        LearningReview.target_id == object_id,
                    )
                )
                or 0
            )
            return page_response(
                await self._review_rows(session, object_id, page, page_size),
                page=page,
                page_size=page_size,
                total=total,
            )

    async def create_explanation(self, body: ExplanationCreate) -> ExplanationAccepted:
        fp = fingerprint(body.model_dump(mode="json", exclude={"request_key"}, exclude_unset=True))
        async with self.sessions.begin() as session:
            await owner_lock(session, self.owner)
            existing = await session.scalar(
                select(KnowledgeRun).where(
                    KnowledgeRun.owner_user_id == self.owner,
                    KnowledgeRun.request_key == body.request_key,
                )
            )
            if existing:
                if existing.input_digest != fp:
                    raise conflict("LEARNING_ASSET_KEY_CONFLICT")
                obj = await self._explanation(session, existing.explanation_id)
                return ExplanationAccepted(
                    explanation=await self._explanation_view(session, obj), run=run_view(existing)
                )
            data = body.model_dump(
                mode="json", exclude={"request_key", "weakness_id", "weakness_version"}
            )
            if body.weakness_id:
                weakness = await self._weakness(session, body.weakness_id, True)
                check_version(weakness.version, cast(int, body.weakness_version))
                if weakness.decision != "confirmed":
                    raise conflict()
                if body.topic and concept_key(body.topic) != weakness.concept_key:
                    raise ValidationAppError(
                        "所选难点与输入主题不同", error_key="KNOWLEDGE_CONFIG_INVALID"
                    )
                explicit_scope = {
                    name for name in SourceConfig.model_fields if name in body.model_fields_set
                }
                if explicit_scope and scope_key(data) != weakness.source_scope_key:
                    raise ValidationAppError(
                        "绑定难点精讲不能改变资料范围", error_key="KNOWLEDGE_CONFIG_INVALID"
                    )
                data.update(weakness.source_config)
                data["topic"] = weakness.title
                if weakness.explanation_id:
                    raise conflict("KNOWLEDGE_RUN_CONFLICT")
            parsed = ExplanationConfig.model_validate(data)
            # Preserve explicit profile-field presence for the shared resolution policy.
            parsed.__pydantic_fields_set__ = set(body.model_fields_set) & set(
                ExplanationConfig.model_fields
            )
            effective = await self._effective(session, parsed)
            data["preferred_language"] = (
                effective.get("values", {}).get("preferred_language") or "zh-CN"
            )
            snapshot = await sources_current(session, self.owner, data)
            obj = KnowledgeExplanation(
                owner_user_id=self.owner,
                weakness_id=body.weakness_id,
                topic=data["topic"],
                config=data,
                effective_context=effective,
                source_snapshot=snapshot,
                request_key=body.request_key,
                input_digest=fp,
                created_by=self.owner,
                updated_by=self.owner,
            )
            session.add(obj)
            await session.flush()
            if body.weakness_id:
                weakness.explanation_id = obj.id
            run = await self._enqueue(session, obj, body.request_key, "generate", fp)
            return ExplanationAccepted(
                explanation=await self._explanation_view(session, obj), run=run_view(run)
            )

    async def list_explanations(self, page: int, page_size: int) -> PageResponse[ExplanationView]:
        async with self.sessions() as session:
            criteria = (
                KnowledgeExplanation.owner_user_id == self.owner,
                KnowledgeExplanation.deleted_at.is_(None),
            )
            total = (
                await session.scalar(
                    select(func.count()).select_from(KnowledgeExplanation).where(*criteria)
                )
                or 0
            )
            rows = list(
                await session.scalars(
                    select(KnowledgeExplanation)
                    .where(*criteria)
                    .order_by(KnowledgeExplanation.updated_at.desc(), KnowledgeExplanation.id)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            return page_response(
                [await self._explanation_view(session, row) for row in rows],
                page=page,
                page_size=page_size,
                total=total,
            )

    async def explanation_detail(self, object_id: UUID) -> ExplanationDetail:
        async with self.sessions() as session:
            obj = await self._explanation(session, object_id)
            view = await self._explanation_view(session, obj)
            card = (
                await session.scalar(
                    select(KnowledgeCardVersion).where(
                        KnowledgeCardVersion.explanation_id == obj.id,
                        KnowledgeCardVersion.version == obj.active_card_version,
                        KnowledgeCardVersion.owner_user_id == self.owner,
                    )
                )
                if obj.active_card_version
                else None
            )
            versions = list(
                await session.scalars(
                    select(KnowledgeCardVersion.version)
                    .where(
                        KnowledgeCardVersion.explanation_id == obj.id,
                        KnowledgeCardVersion.owner_user_id == self.owner,
                    )
                    .order_by(KnowledgeCardVersion.version.desc())
                )
            )
            return ExplanationDetail(
                **view.model_dump(),
                card_versions=versions,
                reviews=await self._review_rows(session, obj.id, 1, 20),
                card=await self._card_view(session, card) if card else None,
                run=await self._latest_run(session, obj.id),
            )

    async def get_card(self, object_id: UUID, version: int) -> KnowledgeCardView:
        async with self.sessions() as session:
            await self._explanation(session, object_id)
            card = await session.scalar(
                select(KnowledgeCardVersion).where(
                    KnowledgeCardVersion.explanation_id == object_id,
                    KnowledgeCardVersion.version == version,
                    KnowledgeCardVersion.owner_user_id == self.owner,
                )
            )
            if card is None:
                raise NotFoundError(error_key="LEARNING_ASSET_NOT_FOUND")
            return await self._card_view(session, card)

    async def explanation_reviews(
        self, object_id: UUID, page: int, page_size: int
    ) -> PageResponse[LearningReviewView]:
        async with self.sessions() as session:
            await self._explanation(session, object_id)
            total = (
                await session.scalar(
                    select(func.count())
                    .select_from(LearningReview)
                    .where(
                        LearningReview.owner_user_id == self.owner,
                        LearningReview.target_id == object_id,
                    )
                )
                or 0
            )
            return page_response(
                await self._review_rows(session, object_id, page, page_size),
                page=page,
                page_size=page_size,
                total=total,
            )

    async def source_preview(self, object_id: UUID, version: int, source_id: str) -> Any:
        from xuemian_ai.document_processing.models import DocumentChunk
        from xuemian_ai.practice.schemas import SourcePreview

        async with self.sessions() as session:
            await self._explanation(session, object_id)
            card = await session.scalar(
                select(KnowledgeCardVersion).where(
                    KnowledgeCardVersion.explanation_id == object_id,
                    KnowledgeCardVersion.version == version,
                    KnowledgeCardVersion.owner_user_id == self.owner,
                )
            )
            if card is None:
                raise NotFoundError(error_key="LEARNING_ASSET_NOT_FOUND")
            payload = KnowledgeCardPayload.model_validate(card.payload)
            source = next((item for item in payload.citations if item.source_id == source_id), None)
            if source is None:
                raise NotFoundError(error_key="LEARNING_ASSET_NOT_FOUND")
            available = await sources_available(
                session, self.owner, card.config, card.source_snapshot
            )
            chunk = (
                await session.scalar(
                    select(DocumentChunk).where(
                        DocumentChunk.id == source.chunk_id,
                        DocumentChunk.user_id == self.owner,
                        DocumentChunk.processing_version_id == source.processing_version_id,
                        DocumentChunk.file_asset_id == source.file_asset_id,
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

    async def regenerate(self, object_id: UUID, body: ExplanationRegenerate) -> ExplanationAccepted:
        fp = fingerprint(
            {
                "explanation_id": object_id,
                **body.model_dump(mode="json", exclude={"request_key"}, exclude_unset=True),
            }
        )
        async with self.sessions.begin() as session:
            await owner_lock(session, self.owner)
            obj = await self._explanation(session, object_id, True)
            previous = await session.scalar(
                select(KnowledgeRun).where(
                    KnowledgeRun.owner_user_id == self.owner,
                    KnowledgeRun.request_key == body.request_key,
                )
            )
            if previous:
                if previous.input_digest != fp:
                    raise conflict("LEARNING_ASSET_KEY_CONFLICT")
                return ExplanationAccepted(
                    explanation=await self._explanation_view(session, obj), run=run_view(previous)
                )
            check_version(obj.version, body.expected_version)
            data = body.config.model_dump(mode="json") if body.config else dict(obj.config)
            if not str(data.get("topic", "")).strip():
                raise ValidationAppError("请输入知识点", error_key="KNOWLEDGE_CONFIG_INVALID")
            if obj.weakness_id:
                weakness = await self._weakness(session, obj.weakness_id)
                if body.config is None:
                    data["topic"] = weakness.title
                if (
                    weakness.decision != "confirmed"
                    or scope_key(data) != weakness.source_scope_key
                    or concept_key(str(data["topic"])) != weakness.concept_key
                ):
                    raise conflict("LEARNING_ASSET_SOURCE_CHANGED")
            snapshot = await sources_current(session, self.owner, data)
            if obj.weakness_id and fingerprint(snapshot) != fingerprint(weakness.source_snapshot):
                previous_snapshot = weakness.source_snapshot
                weakness.source_snapshot = snapshot
                weakness.version += 1
                weakness.last_user_action_at = datetime.now(UTC)
                event(
                    session,
                    weakness,
                    "source_refreshed",
                    self.owner,
                    {
                        "previous_snapshot_digest": fingerprint(previous_snapshot),
                        "snapshot_digest": fingerprint(snapshot),
                    },
                )
            config = body.config or ExplanationConfig.model_validate(data)
            effective = await self._effective(session, config)
            data["preferred_language"] = (
                effective.get("values", {}).get("preferred_language") or "zh-CN"
            )
            obj.version += 1
            obj.config, obj.source_snapshot, obj.effective_context = data, snapshot, effective
            obj.topic, obj.updated_by = str(data["topic"]), self.owner
            run = await self._enqueue(session, obj, body.request_key, "regenerate", fp)
            return ExplanationAccepted(
                explanation=await self._explanation_view(session, obj), run=run_view(run)
            )

    async def delete_explanation(self, object_id: UUID, expected_version: int) -> None:
        async with self.sessions.begin() as session:
            await owner_lock(session, self.owner)
            obj = await self._explanation(session, object_id, True)
            check_version(obj.version, expected_version)
            obj.deleted_at, obj.deleted_by, obj.version = (
                datetime.now(UTC),
                self.owner,
                obj.version + 1,
            )
            runs = list(
                await session.scalars(
                    select(KnowledgeRun)
                    .where(
                        KnowledgeRun.explanation_id == obj.id, KnowledgeRun.status.in_(ACTIVE_RUNS)
                    )
                    .with_for_update()
                )
            )
            for run in runs:
                run.status = "cancelled" if run.status == "pending" else "cancel_requested"
                if run.status == "cancelled":
                    run.stage, run.ended_at = "cancelled", datetime.now(UTC)

    async def get_run(self, run_id: UUID) -> KnowledgeRunView:
        async with self.sessions() as session:
            return run_view(await self._run(session, run_id))

    async def lookup_run(self, request_key: UUID) -> KnowledgeRunView:
        async with self.sessions() as session:
            run = await session.scalar(
                select(KnowledgeRun).where(
                    KnowledgeRun.owner_user_id == self.owner,
                    KnowledgeRun.request_key == request_key,
                )
            )
            if run is None:
                raise NotFoundError(error_key="LEARNING_ASSET_NOT_FOUND")
            return run_view(run)

    async def cancel(self, run_id: UUID) -> KnowledgeRunView:
        async with self.sessions.begin() as session:
            run = await self._run(session, run_id, True)
            if run.status == "pending":
                run.status, run.stage, run.ended_at = "cancelled", "cancelled", datetime.now(UTC)
            elif run.status == "processing":
                run.status = "cancel_requested"
            elif run.status not in {"cancel_requested", "cancelled"}:
                raise conflict("KNOWLEDGE_RUN_CONFLICT")
            await session.flush()
            return run_view(run)

    async def retry(self, run_id: UUID, request_key: UUID, input_digest: str) -> KnowledgeRunView:
        async with self.sessions.begin() as session:
            await owner_lock(session, self.owner)
            run = await self._run(session, run_id, True)
            if (
                run.request_key != request_key
                or run.input_digest != input_digest
                or run.status != "failed"
                or not run.retryable
            ):
                raise conflict("KNOWLEDGE_RUN_CONFLICT")
            if not await self._execution_account(session, run.owner_user_id):
                raise NotFoundError(error_key="LEARNING_ASSET_NOT_FOUND")
            obj = await self._explanation(session, run.explanation_id, True)
            check_version(obj.version, run.expected_version)
            if not await sources_available(
                session, self.owner, obj.config, run.input_snapshot["source_snapshot"]
            ):
                raise conflict("LEARNING_ASSET_SOURCE_CHANGED")
            await self._fence_weakness(session, run)
            run.status, run.stage, run.error_key, run.retryable = "pending", "waiting", None, False
            run.lease_token, run.lease_owner, run.lease_expires_at = None, None, None
            run.started_at, run.ended_at = None, None
            await session.flush()
            return run_view(run)

    async def _execution_account(self, session: AsyncSession, owner: UUID) -> bool:
        return (
            await session.scalar(
                select(User.id)
                .where(
                    User.id == owner,
                    User.status == "active",
                    User.role == "user",
                    User.deleted_at.is_(None),
                )
                .with_for_update(read=True)
            )
            is not None
        )

    async def _fence_weakness(self, session: AsyncSession, run: KnowledgeRun) -> None:
        if run.input_snapshot.get("weakness_id"):
            obj = await self._weakness(session, UUID(run.input_snapshot["weakness_id"]), True)
            if obj.decision != "confirmed" or obj.version != run.input_snapshot.get(
                "weakness_version"
            ):
                raise conflict("LEARNING_ASSET_SOURCE_CHANGED")

    async def recover_expired(self) -> int:
        async with self.sessions.begin() as session:
            now = datetime.now(UTC)
            rows = list(
                await session.scalars(
                    select(KnowledgeRun)
                    .where(
                        KnowledgeRun.status.in_(("processing", "cancel_requested")),
                        KnowledgeRun.lease_expires_at < now,
                    )
                    .with_for_update(skip_locked=True)
                )
            )
            for run in rows:
                run.status = "cancelled" if run.status == "cancel_requested" else "failed"
                run.stage, run.ended_at = run.status, now
                run.error_key = None if run.status == "cancelled" else "KNOWLEDGE_RUN_TIMEOUT"
                run.retryable = run.status == "failed"
                run.lease_token, run.lease_expires_at = None, None
            return len(rows)

    async def claim_run(self, worker_id: str) -> KnowledgeRun | None:
        async with self.sessions.begin() as session:
            run = await session.scalar(
                select(KnowledgeRun)
                .where(KnowledgeRun.status == "pending")
                .order_by(KnowledgeRun.created_at, KnowledgeRun.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if run is None:
                return None
            now = datetime.now(UTC)
            if not await self._execution_account(session, run.owner_user_id):
                run.status, run.stage, run.error_key, run.retryable, run.ended_at = (
                    "failed",
                    "failed",
                    "LEARNING_ASSET_NOT_FOUND",
                    False,
                    now,
                )
                return None
            run.status, run.stage, run.started_at = "processing", "preflight", now
            run.lease_owner, run.lease_token = worker_id, uuid4()
            run.lease_expires_at = now + timedelta(
                seconds=getattr(self.settings, "knowledge_worker_lease_seconds", 30)
            )
            run.attempt_count += 1
            await session.flush()
            session.expunge(run)
            return run

    async def heartbeat(self, run_id: UUID, token: UUID, stage: str | None = None) -> bool:
        async with self.sessions.begin() as session:
            owner = await session.scalar(
                select(KnowledgeRun.owner_user_id).where(KnowledgeRun.id == run_id)
            )
            if owner is None:
                return False
            await owner_lock(session, owner)
            run = await session.scalar(
                select(KnowledgeRun).where(KnowledgeRun.id == run_id).with_for_update()
            )
            now = datetime.now(UTC)
            if (
                run is None
                or run.lease_token != token
                or run.status != "processing"
                or not run.lease_expires_at
                or run.lease_expires_at <= now
            ):
                return False
            timeout = getattr(self.settings, "knowledge_run_timeout_seconds", 180)
            if run.started_at and run.started_at + timedelta(seconds=timeout) <= now:
                run.status, run.stage, run.error_key, run.retryable = (
                    "failed",
                    "failed",
                    "KNOWLEDGE_RUN_TIMEOUT",
                    True,
                )
                run.ended_at, run.lease_token = now, None
                return False
            domain = LearningAssetService(self.sessions, run.owner_user_id, self.settings)
            if not await domain._execution_account(session, run.owner_user_id):
                raise NotFoundError(error_key="LEARNING_ASSET_NOT_FOUND")
            obj = await domain._explanation(session, run.explanation_id)
            check_version(obj.version, run.expected_version)
            await domain._fence_weakness(session, run)
            if not await sources_available(
                session,
                run.owner_user_id,
                run.input_snapshot["config"],
                run.input_snapshot["source_snapshot"],
            ):
                raise conflict("LEARNING_ASSET_SOURCE_CHANGED")
            run.lease_expires_at = now + timedelta(
                seconds=getattr(self.settings, "knowledge_worker_lease_seconds", 30)
            )
            if stage:
                run.stage = stage
            return True

    async def publish_run(
        self,
        run_id: UUID,
        token: UUID,
        payload: dict[str, Any],
        manifest: dict[str, Any] | None = None,
    ) -> bool:
        validated = KnowledgeCardPayload.model_validate(payload)
        async with self.sessions.begin() as session:
            await owner_lock(session, self.owner)
            run = await self._run(session, run_id, True)
            now = datetime.now(UTC)
            if (
                run.lease_token != token
                or run.status not in {"processing", "cancel_requested"}
                or not run.lease_expires_at
                or run.lease_expires_at <= now
            ):
                return False
            if run.status == "cancel_requested":
                run.status, run.stage, run.ended_at = "cancelled", "cancelled", now
                return False
            if (
                run.started_at
                and run.started_at
                + timedelta(seconds=getattr(self.settings, "knowledge_run_timeout_seconds", 180))
                <= now
            ):
                run.status, run.stage, run.ended_at = "failed", "failed", now
                run.error_key, run.retryable, run.lease_token = "KNOWLEDGE_RUN_TIMEOUT", True, None
                return False
            if not await self._execution_account(session, run.owner_user_id):
                raise NotFoundError(error_key="LEARNING_ASSET_NOT_FOUND")
            obj = await self._explanation(session, run.explanation_id, True)
            check_version(obj.version, run.expected_version)
            await self._fence_weakness(session, run)
            if not await sources_available(
                session,
                self.owner,
                run.input_snapshot["config"],
                run.input_snapshot["source_snapshot"],
            ):
                raise conflict("LEARNING_ASSET_SOURCE_CHANGED")
            if validated.source_mode != run.input_snapshot["config"]["source_mode"]:
                raise ValidationAppError("生成来源不一致", error_key="KNOWLEDGE_OUTPUT_INVALID")
            allowed = {
                (item["file_id"], item["file_asset_id"], item["processing_version_id"])
                for item in run.input_snapshot["source_snapshot"]
            }
            for citation in validated.citations:
                if (
                    str(citation.file_id),
                    str(citation.file_asset_id),
                    str(citation.processing_version_id),
                ) not in allowed:
                    raise ValidationAppError(
                        "引用不属于任务资料", error_key="KNOWLEDGE_OUTPUT_INVALID"
                    )
                from xuemian_ai.document_processing.models import DocumentChunk

                chunk = await session.scalar(
                    select(DocumentChunk.id).where(
                        DocumentChunk.id == citation.chunk_id,
                        DocumentChunk.processing_version_id == citation.processing_version_id,
                        DocumentChunk.user_id == self.owner,
                        DocumentChunk.file_asset_id == citation.file_asset_id,
                    )
                )
                if chunk is None:
                    raise ValidationAppError("引用无法定位", error_key="KNOWLEDGE_OUTPUT_INVALID")
            version = (
                await session.scalar(
                    select(func.max(KnowledgeCardVersion.version)).where(
                        KnowledgeCardVersion.explanation_id == obj.id
                    )
                )
                or 0
            ) + 1
            card = KnowledgeCardVersion(
                owner_user_id=self.owner,
                explanation_id=obj.id,
                version=version,
                parent_version=obj.active_card_version,
                payload=validated.model_dump(mode="json"),
                config=run.input_snapshot["config"],
                source_snapshot=run.input_snapshot["source_snapshot"],
                manifest=manifest or {},
                run_id=run.id,
            )
            session.add(card)
            await session.flush()
            obj.active_card_version = version
            run.status, run.stage, run.ended_at = "succeeded", "completed", now
            run.result_ref = {
                "type": "card",
                "id": str(card.id),
                "explanation_id": str(obj.id),
                "version": version,
            }
            run.manifest, run.lease_token = manifest or {}, None
            return True

    async def fail_run(self, run_id: UUID, token: UUID, error_key: str, retryable: bool) -> None:
        async with self.sessions.begin() as session:
            run = await self._run(session, run_id, True)
            if run.lease_token != token or run.status not in {"processing", "cancel_requested"}:
                return
            cancelled = run.status == "cancel_requested"
            run.status, run.stage = (
                ("cancelled", "cancelled") if cancelled else ("failed", "failed")
            )
            run.error_key, run.retryable = (None, False) if cancelled else (error_key, retryable)
            run.ended_at, run.lease_token = datetime.now(UTC), None


async def list_active_weaknesses(session: AsyncSession, owner: UUID) -> list[Any]:
    from xuemian_ai.profiles.schemas import ActiveWeaknessView

    objects = list(
        await session.scalars(
            select(Weakness)
            .where(
                Weakness.owner_user_id == owner,
                Weakness.deleted_at.is_(None),
                Weakness.decision == "confirmed",
                Weakness.mastery_state != "mastered",
            )
            .order_by(Weakness.updated_at.desc(), Weakness.id)
        )
    )
    result = []
    for obj in objects:
        evidence = list(
            await session.scalars(
                select(WeaknessEvidence).where(
                    WeaknessEvidence.weakness_id == obj.id,
                    WeaknessEvidence.owner_user_id == owner,
                    WeaknessEvidence.superseded.is_(False),
                    WeaknessEvidence.ignored.is_(False),
                )
            )
        )
        available = [
            item for item in evidence if await evidence_available(session, owner, obj, item)
        ]
        if not available:
            continue
        review = await session.scalar(
            select(LearningReview)
            .where(
                LearningReview.target_id == obj.id,
                LearningReview.owner_user_id == owner,
                LearningReview.validation_passed.is_(True),
            )
            .order_by(LearningReview.created_at.desc())
            .limit(1)
        )
        result.append(
            ActiveWeaknessView(
                id=obj.id,
                name=obj.title,
                domain=obj.domain,
                severity=cast(Any, obj.severity),
                mastery_status=obj.mastery_state,
                source_summary="用户主动学习目标"
                if all(item.kind == "manual" for item in available)
                else "练习评分证据",
                last_verified_at=review.created_at.isoformat() if review else None,
            )
        )
    return result
