"""Transactional durable practice evidence projections, including review completion."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from xuemian_ai.learning_assets.models import (
    LearningEvidenceEvent,
    LearningReview,
    Weakness,
    WeaknessEvent,
    WeaknessEvidence,
)
from xuemian_ai.learning_assets.policy import (
    Observation,
    automatic_confirmation,
    concept_key,
    fingerprint,
    review_conclusion,
    scope_key,
)
from xuemian_ai.learning_assets.service import (
    LearningAssetService,
    event,
    evidence_available,
    owner_lock,
    sources_available,
)
from xuemian_ai.practice.models import (
    PracticeAttempt,
    PracticeGrade,
    PracticeRevision,
    PracticeSet,
    PracticeSubmission,
)


async def append_evidence_event(
    session: AsyncSession, owner: UUID, event_type: str, object_id: UUID, object_version: int
) -> None:
    if event_type not in {
        "grade_published",
        "submission_published",
        "attempt_completed",
        "set_deleted",
    }:
        raise ValueError("unsupported learning evidence event")
    await session.execute(
        insert(LearningEvidenceEvent)
        .values(
            owner_user_id=owner,
            event_type=event_type,
            object_id=object_id,
            object_version=object_version,
        )
        .on_conflict_do_nothing(constraint="uq_learning_outbox_event")
    )


class LearningProjection:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], settings: Any = None) -> None:
        self.sessions, self.settings = sessions, settings

    async def process_next(self) -> bool:
        async with self.sessions.begin() as session:
            item = await session.scalar(
                select(LearningEvidenceEvent)
                .where(LearningEvidenceEvent.processed_at.is_(None))
                .order_by(LearningEvidenceEvent.created_at, LearningEvidenceEvent.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if item is None:
                return False
            await owner_lock(session, item.owner_user_id)
            await self._recompute(session, item.owner_user_id)
            item.processed_at = datetime.now(UTC)
            return True

    async def process_evidence_event(self, event_id: UUID) -> bool:
        async with self.sessions.begin() as session:
            item = await session.scalar(
                select(LearningEvidenceEvent)
                .where(LearningEvidenceEvent.id == event_id)
                .with_for_update()
            )
            if item is None or item.processed_at is not None:
                return False
            await owner_lock(session, item.owner_user_id)
            await self._recompute(session, item.owner_user_id)
            item.processed_at = datetime.now(UTC)
            return True

    async def _recompute(self, session: AsyncSession, owner: UUID) -> None:
        # Read authoritative latest submission first: a new ungraded answer cannot reuse old grade.
        rows = (
            await session.execute(
                select(PracticeSubmission, PracticeAttempt, PracticeRevision, PracticeSet)
                .join(PracticeAttempt, PracticeSubmission.attempt_id == PracticeAttempt.id)
                .join(PracticeRevision, PracticeAttempt.revision_id == PracticeRevision.id)
                .join(PracticeSet, PracticeAttempt.set_id == PracticeSet.id)
                .where(
                    PracticeSubmission.owner_user_id == owner,
                    PracticeAttempt.owner_user_id == owner,
                    PracticeRevision.owner_user_id == owner,
                    PracticeSet.owner_user_id == owner,
                )
                .order_by(PracticeSubmission.created_at, PracticeSubmission.id)
            )
        ).all()
        latest: dict[
            tuple[UUID, UUID],
            tuple[PracticeSubmission, PracticeAttempt, PracticeRevision, PracticeSet],
        ] = {}
        for sub, attempt, revision, obj in rows:
            latest[(attempt.id, sub.question_id)] = sub, attempt, revision, obj
        grades = list(
            await session.scalars(
                select(PracticeGrade)
                .where(PracticeGrade.owner_user_id == owner)
                .order_by(PracticeGrade.version)
            )
        )
        by_submission = {grade.submission_id: grade for grade in grades}
        eligible_grades = set(
            await session.scalars(
                select(LearningEvidenceEvent.object_id).where(
                    LearningEvidenceEvent.owner_user_id == owner,
                    LearningEvidenceEvent.event_type == "grade_published",
                )
            )
        )
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        available_sources: dict[UUID, bool] = {}
        for sub, attempt, revision, obj in latest.values():
            if revision.id not in available_sources:
                available_sources[revision.id] = obj.deleted_at is None and await sources_available(
                    session, owner, revision.config, revision.source_snapshot
                )
            grade = by_submission.get(sub.id)
            if grade is not None and grade.id not in eligible_grades:
                grade = None
            topics = list(
                dict.fromkeys(
                    str(topic).strip()
                    for topic in sub.question.get("topics", [])
                    if str(topic).strip()
                )
            )
            for topic in topics:
                if len(concept_key(topic)) > 500:
                    continue
                key = scope_key(revision.config), concept_key(topic)
                grouped.setdefault(key, []).append(
                    {
                        "sub": sub,
                        "attempt": attempt,
                        "revision": revision,
                        "grade": grade,
                        "topic": topic,
                        "available": available_sources[revision.id],
                        "single": len(topics) == 1,
                    }
                )
        assets = list(
            await session.scalars(
                select(Weakness)
                .where(Weakness.owner_user_id == owner)
                .order_by(Weakness.created_at)
            )
        )
        active = {
            (obj.source_scope_key, obj.concept_key): obj for obj in assets if obj.deleted_at is None
        }
        tombstones = {
            (obj.source_scope_key, obj.concept_key): obj
            for obj in assets
            if obj.deleted_at is not None
        }
        assigned = list(
            await session.scalars(
                select(WeaknessEvidence).where(
                    WeaknessEvidence.owner_user_id == owner, WeaknessEvidence.kind == "practice"
                )
            )
        )
        by_asset = {obj.id: obj for obj in assets}
        aliases: dict[tuple[str, str], Weakness] = {}
        tombstone_aliases: dict[tuple[str, str], Weakness] = {}
        for assigned_item in assigned:
            assigned_asset = by_asset.get(assigned_item.weakness_id)
            if assigned_asset and assigned_item.source_key.startswith("grade:"):
                alias_key = (
                    assigned_asset.source_scope_key,
                    assigned_item.source_key.rsplit(":", 1)[-1],
                )
                if assigned_asset.deleted_at is None:
                    aliases[alias_key] = assigned_asset
                else:
                    previous_tombstone = tombstone_aliases.get(alias_key)
                    if (
                        previous_tombstone is None
                        or assigned_asset.created_at > previous_tombstone.created_at
                    ):
                        tombstone_aliases[alias_key] = assigned_asset
        # Resolve aliases before applying replacement rules. A rename and its new targeted
        # questions share one asset: replacing evidence per textual topic would let the
        # groups incorrectly supersede each other on every outbox replay.
        resolved_groups: dict[tuple[str, str], dict[str, Any]] = {}
        for key, grouped_rows in grouped.items():
            resolved_asset = active.get(key) or aliases.get((key[0], fingerprint(key[1])))
            resolved_tombstone = (
                None
                if resolved_asset
                else (tombstones.get(key) or tombstone_aliases.get((key[0], fingerprint(key[1]))))
            )
            if resolved_asset:
                identity = ("asset", str(resolved_asset.id))
            elif resolved_tombstone:
                identity = ("tombstone", str(resolved_tombstone.id))
            else:
                identity = ("concept", fingerprint(key))
            group = resolved_groups.setdefault(
                identity,
                {"key": key, "obj": resolved_asset, "tombstone": resolved_tombstone, "rows": []},
            )
            group["rows"].extend(grouped_rows)
        projected_ids: set[UUID] = set()
        domain = LearningAssetService(self.sessions, owner, self.settings)
        for group in resolved_groups.values():
            key, evidence, obj = group["key"], group["rows"], group["obj"]
            newest: dict[UUID, dict[str, Any]] = {}
            for row in evidence:
                previous = newest.get(row["sub"].question_id)
                if previous is None or (row["sub"].created_at, str(row["sub"].id)) > (
                    previous["sub"].created_at,
                    str(previous["sub"].id),
                ):
                    newest[row["sub"].question_id] = row
            evidence = list(newest.values())
            wrong = [
                row
                for row in evidence
                if row["grade"]
                and row["grade"].payload.get("level") in {"incorrect", "partial"}
                and row["available"]
            ]
            if obj is None and wrong:
                tombstone = group["tombstone"]
                blocked = set(tombstone.blocked_question_ids) if tombstone else set()
                if tombstone:
                    old = list(
                        await session.scalars(
                            select(WeaknessEvidence.question_id).where(
                                WeaknessEvidence.weakness_id == tombstone.id,
                                WeaknessEvidence.question_id.is_not(None),
                            )
                        )
                    )
                    blocked.update(str(item) for item in old)
                new = [row for row in wrong if str(row["sub"].question_id) not in blocked]
                if not new:
                    continue
                original = new[-1]
                revision = original["revision"]
                source = {
                    "source_mode": revision.config.get("source_mode", "general"),
                    "knowledge_base_id": revision.config.get("knowledge_base_id"),
                    "file_ids": revision.config.get("file_ids", []),
                }
                obj = Weakness(
                    owner_user_id=owner,
                    title=original["topic"][:120],
                    concept_key=concept_key(original["topic"]),
                    source_scope_key=key[0],
                    source_config=source,
                    source_snapshot=revision.source_snapshot,
                    tags=[],
                    severity="medium",
                    decision="pending",
                    blocked_question_ids=sorted(blocked),
                )
                session.add(obj)
                await session.flush()
                active[(obj.source_scope_key, obj.concept_key)] = obj
                event(
                    session, obj, "candidate_created", None, {"restored_candidate": bool(tombstone)}
                )
                if tombstone:
                    event(session, obj, "revocation_barrier", None)
            if obj is None:
                continue
            projected_ids.add(obj.id)
            existing = list(
                await session.scalars(
                    select(WeaknessEvidence).where(WeaknessEvidence.weakness_id == obj.id)
                )
            )
            by_key = {item.source_key: item for item in existing}
            valid_keys: set[str] = set()
            observations = []
            has_new_wrong = False
            restored_ids: list[str] = []
            for row in evidence:
                sub, grade = row["sub"], row["grade"]
                if grade is None:
                    continue
                source_id = f"grade:{grade.id}:{fingerprint(concept_key(row['topic']))}"
                valid_keys.add(source_id)
                item = by_key.get(source_id)
                ignored = str(sub.question_id) in set(obj.blocked_question_ids)
                low = (
                    sub.question.get("type") in {"short_answer", "code_text"}
                    and float(grade.payload.get("confidence", 0)) < 0.7
                )
                if item is None:
                    item = WeaknessEvidence(
                        owner_user_id=owner,
                        weakness_id=obj.id,
                        kind="practice",
                        source_key=source_id,
                        question_id=sub.question_id,
                        attempt_id=row["attempt"].id,
                        revision_id=row["revision"].id,
                        submission_id=sub.id,
                        grade_id=grade.id,
                        grade_version=grade.version,
                        submitted_at=sub.created_at,
                        ignored=ignored,
                        detail={
                            "level": grade.payload.get("level"),
                            "difficulty": sub.question.get("difficulty", "medium"),
                            "single_topic": row["single"],
                            "low_confidence": low,
                            "error_reasons": grade.payload.get("error_reasons", []),
                            "missing_points": grade.payload.get("missing_points", []),
                            "confidence": grade.payload.get("confidence"),
                            "attribution": "single_topic"
                            if row["single"]
                            else "whole_question_unverified",
                        },
                    )
                    session.add(item)
                    if (
                        row["available"]
                        and not ignored
                        and grade.payload.get("level") in {"incorrect", "partial"}
                    ):
                        has_new_wrong = True
                if item.superseded:
                    item.superseded = False
                    restored_ids.append(str(item.id))
                observations.append(
                    Observation(
                        question_id=sub.question_id,
                        attempt_id=row["attempt"].id,
                        submitted_at=sub.created_at,
                        level=grade.payload.get("level", "incorrect"),
                        difficulty=sub.question.get("difficulty", "medium"),
                        single_topic=row["single"],
                        low_confidence=low,
                        available=row["available"],
                        ignored=ignored or item.ignored,
                    )
                )
            if restored_ids:
                event(
                    session,
                    obj,
                    "evidence_restored",
                    None,
                    {"restored_ids": restored_ids, "reason": "authoritative_latest"},
                )
            corrections = []
            for item in existing:
                if (
                    item.kind == "practice"
                    and not item.superseded
                    and item.source_key not in valid_keys
                ):
                    item.superseded = True
                    corrections.append(str(item.id))
            if corrections:
                event(session, obj, "evidence_corrected", None, {"superseded_ids": corrections})
            was_revoked = obj.decision == "revoked" or bool(
                await session.scalar(
                    select(WeaknessEvent.id)
                    .where(
                        WeaknessEvent.weakness_id == obj.id,
                        WeaknessEvent.event_type.in_(("revoked", "revocation_barrier")),
                    )
                    .limit(1)
                )
            )
            if has_new_wrong and obj.decision in {"ignored", "revoked"}:
                obj.decision = "pending"
                obj.version += 1
                event(session, obj, "candidate_reopened", None)
            sufficient = automatic_confirmation(observations, datetime.now(UTC))
            obj.evidence_sufficient = sufficient or any(
                item.kind == "manual" and not item.ignored for item in existing
            )
            if obj.decision == "pending" and sufficient and not was_revoked:
                obj.decision = "confirmed"
                obj.version += 1
                event(session, obj, "auto_confirmed", None, {"policy_version": obj.policy_version})
                await domain._first_card(session, obj)
        await session.flush()
        # Invalidated/deleted sources may remove every grade without introducing a new topic.
        for obj in active.values():
            if obj.id not in projected_ids:
                manual = list(
                    await session.scalars(
                        select(WeaknessEvidence).where(
                            WeaknessEvidence.weakness_id == obj.id,
                            WeaknessEvidence.kind == "manual",
                            WeaknessEvidence.ignored.is_(False),
                        )
                    )
                )
                obj.evidence_sufficient = any(
                    [await evidence_available(session, owner, obj, item) for item in manual]
                )
        attempts = (
            await session.execute(
                select(PracticeAttempt, PracticeRevision, PracticeSet)
                .join(PracticeRevision, PracticeAttempt.revision_id == PracticeRevision.id)
                .join(PracticeSet, PracticeAttempt.set_id == PracticeSet.id)
                .where(
                    PracticeAttempt.owner_user_id == owner,
                    PracticeRevision.owner_user_id == owner,
                    PracticeSet.owner_user_id == owner,
                )
            )
        ).all()
        for attempt, revision, obj in attempts:
            target = revision.effective_context.get("learning_target")
            if not target:
                continue
            await self._review(
                session, owner, attempt, revision, obj, target, latest, by_submission
            )

    async def _review(
        self,
        session: AsyncSession,
        owner: UUID,
        attempt: PracticeAttempt,
        revision: PracticeRevision,
        obj: PracticeSet,
        target: dict[str, Any],
        latest: dict[Any, Any],
        grades: dict[UUID, PracticeGrade],
    ) -> None:
        topic = concept_key(
            str(target.get("topic") or target.get("concept") or revision.config.get("topic", ""))
        )
        related = [
            question
            for question in revision.questions
            if len(question.get("topics", [])) == 1
            and concept_key(str(question["topics"][0])) == topic
        ]
        submitted = graded = correct = low = 0
        wrong_times = []
        refs = []
        for question in related:
            row = latest.get((attempt.id, UUID(str(question["question_id"]))))
            if row is None:
                refs.append({"question": question["question_id"], "submission": None})
                continue
            sub = row[0]
            submitted += 1
            grade = grades.get(sub.id)
            refs.append(
                {
                    "question": question["question_id"],
                    "submission": str(sub.id),
                    "grade": str(grade.id) if grade else None,
                }
            )
            if grade is None:
                continue
            graded += 1
            is_low = (
                question.get("type") in {"short_answer", "code_text"}
                and float(grade.payload.get("confidence", 0)) < 0.7
            )
            low += int(is_low)
            correct += int(grade.payload.get("level") == "correct")
            if not is_low and grade.payload.get("level") in {"incorrect", "partial"}:
                wrong_times.append(sub.created_at)
        available = obj.deleted_at is None and await sources_available(
            session, owner, revision.config, revision.source_snapshot
        )
        passed, conclusion = review_conclusion(
            len(related), submitted, graded, correct, low, attempt.status == "completed", available
        )
        fp = fingerprint({"refs": refs, "completed": attempt.status, "source_available": available})
        prior = list(
            await session.scalars(
                select(LearningReview)
                .where(
                    LearningReview.attempt_id == attempt.id, LearningReview.owner_user_id == owner
                )
                .order_by(LearningReview.version)
            )
        )
        if prior:
            previous_digest = prior[-2].input_digest if len(prior) > 1 else None
            latest_digest = fingerprint({"input": fp, "previous": previous_digest})
            # 只与最新结论去重：来源 A→失效 B→恢复 A 仍需要追加恢复记录。
            # 兼容旧版直接保存内容摘要的历史；新版本串入前一摘要，既保留
            # 相同投影重放的幂等性，也满足数据库对 attempt/input_digest 的唯一约束。
            if prior[-1].input_digest in {fp, latest_digest}:
                return
            fp = fingerprint({"input": fp, "previous": prior[-1].input_digest})
        session.add(
            LearningReview(
                owner_user_id=owner,
                target_kind=target["kind"],
                target_id=UUID(str(target["id"])),
                target_snapshot=target,
                set_id=obj.id,
                attempt_id=attempt.id,
                version=(prior[-1].version + 1) if prior else 1,
                input_digest=fp,
                source_available=available,
                total_related=len(related),
                submitted_count=submitted,
                graded_count=graded,
                correct_count=correct,
                low_confidence_count=low,
                validation_passed=passed,
                conclusion=conclusion,
            )
        )
        if target["kind"] == "weakness" and wrong_times and available:
            weakness = await session.scalar(
                select(Weakness)
                .where(
                    Weakness.id == UUID(str(target["id"])),
                    Weakness.owner_user_id == owner,
                    Weakness.deleted_at.is_(None),
                )
                .with_for_update()
            )
            # A newer explicit user status fences late events/regrades from older answers.
            if (
                weakness
                and weakness.decision == "confirmed"
                and weakness.mastery_state in {"to_verify", "mastered"}
                and max(wrong_times) > (weakness.last_user_action_at or attempt.started_at)
            ):
                old = weakness.mastery_state
                weakness.mastery_state, weakness.version = "learning", weakness.version + 1
                event(
                    session,
                    weakness,
                    "validation_regressed",
                    None,
                    {"attempt_id": str(attempt.id), "from": old, "reason": "new_valid_error"},
                )
