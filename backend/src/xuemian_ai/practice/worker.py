"""Persistent, bounded practice execution; domain repository owns all publication fencing."""

import asyncio
import contextlib
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypedDict
from uuid import UUID, uuid4

from langgraph.graph import END, START, StateGraph
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from xuemian_ai.agent_runs.contracts import ManagedPromptSnapshot, canonical_hash
from xuemian_ai.core.config import Settings, get_settings
from xuemian_ai.core.errors import AppError, UpstreamServiceError, ValidationAppError
from xuemian_ai.core.logging import bind_context, configure_logging, get_logger
from xuemian_ai.document_processing.retrieval import RetrievalService
from xuemian_ai.document_processing.schemas import EvidenceChunk, RetrievalRequest
from xuemian_ai.document_processing.vector_store import VectorStore
from xuemian_ai.infrastructure.resources import Infrastructure
from xuemian_ai.practice.context import PROFILE_FIELDS, ensure_general_topic
from xuemian_ai.practice.generation import (
    PracticeProvider,
    QwenPracticeProvider,
    generation_schema,
    prompt_manifest,
    subjective_provider_schema,
    validate_question_snapshots,
    validate_questions,
)
from xuemian_ai.practice.grading import validate_subjective_grade
from xuemian_ai.practice.schemas import GradePayload, PracticeConfig, QuestionSnapshot

_logger = get_logger(__name__)


class ClaimedRun(Protocol):
    @property
    def id(self) -> UUID: ...
    @property
    def owner_user_id(self) -> UUID: ...
    @property
    def operation(self) -> str: ...
    @property
    def input_snapshot(self) -> dict[str, Any]: ...
    @property
    def lease_token(self) -> UUID | None: ...


@dataclass(frozen=True)
class RunClaim:
    id: UUID
    owner_user_id: UUID
    operation: str
    input_snapshot: dict[str, Any]
    lease_token: UUID


class RunRepository(Protocol):
    async def claim_run(self, worker_id: str, lease_seconds: int) -> Any: ...
    async def heartbeat(
        self, run_id: UUID, token: UUID, lease_seconds: int, stage: str
    ) -> bool: ...
    async def publish_run(
        self,
        run_id: UUID,
        token: UUID,
        result: dict[str, Any],
        manifest: dict[str, object] | None = None,
    ) -> bool: ...
    async def fail_run(
        self, run_id: UUID, token: UUID, error_key: str, retryable: bool
    ) -> bool: ...
    async def expire_runs(self) -> Any: ...


class ExecutionState(TypedDict, total=False):
    config: dict[str, Any]
    evidence: list[EvidenceChunk]
    trace_ids: list[str]
    raw: dict[str, Any]
    result: dict[str, Any]


class LeaseLost(Exception):
    pass


class PracticeWorker:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
        provider: PracticeProvider | None = None,
        store: VectorStore | None = None,
        repository: RunRepository | None = None,
        retrieve: Callable[
            [ClaimedRun, dict[str, Any]], Awaitable[tuple[list[EvidenceChunk], list[str]]]
        ]
        | None = None,
    ) -> None:
        from xuemian_ai.practice.service import PracticeService

        self.sessions, self.settings = sessions, settings
        self.provider = provider or QwenPracticeProvider(settings)
        self.store = store
        self.repository: RunRepository = repository or PracticeService(
            sessions, UUID(int=0), settings
        )
        self.retrieve_override = retrieve
        self.worker_id = str(uuid4())

    async def checkpoint(self, run: ClaimedRun, stage: str) -> None:
        if run.lease_token is None or not await self.repository.heartbeat(
            run.id,
            run.lease_token,
            self.settings.practice_worker_lease_seconds,
            stage,
        ):
            raise LeaseLost()

    async def retrieve(
        self,
        run: ClaimedRun,
        config: dict[str, Any],
    ) -> tuple[list[EvidenceChunk], list[str]]:
        if self.retrieve_override:
            return await self.retrieve_override(run, config)
        service = RetrievalService(
            self.sessions, self.settings, run.owner_user_id, str(run.id), vector_store=self.store
        )
        values = run.input_snapshot.get("effective_context", {}).get("values", {})
        query = config.get("topic") or " ".join(
            values.get("focus_topics") or values.get("target_skills") or []
        )
        query = query or values.get("target_job") or "知识要点"
        try:
            result = await service.search(
                UUID(config["knowledge_base_id"]),
                RetrievalRequest(
                    query=str(query)[:2000],
                    file_ids=[
                        UUID(source["file_id"])
                        for source in run.input_snapshot.get("source_snapshot", [])
                    ],
                    top_n=8,
                ),
            )
            return result.evidence, [str(result.trace_id)]
        finally:
            if service.owns_store:
                await service.vector_store.close()

    async def execute(self, run: ClaimedRun) -> None:
        snapshot = run.input_snapshot
        operation = run.operation
        config = dict(snapshot.get("revision_config") or snapshot.get("config", {}))
        target: dict[str, Any] | None = None
        if operation == "regenerate":
            original = snapshot.get("questions", [])
            if snapshot.get("question_id"):
                target = next(
                    (q for q in original if q["question_id"] == snapshot["question_id"]), None
                )
                if target is None:
                    raise ValidationAppError(error_key="PRACTICE_CONFIG_INVALID")
                config.update(
                    question_count=1,
                    question_types={target["type"]: 1},
                    difficulty=target["difficulty"],
                )
            else:
                config.update(
                    question_count=len(original),
                    question_types=dict(Counter(q["type"] for q in original)),
                )
        schema = (
            subjective_provider_schema(snapshot["question"], snapshot["answer"])
            if operation in {"grade", "regrade"}
            else (
                PracticeConfig.model_json_schema()
                if operation == "plan"
                else generation_schema(config)
            )
        )
        manifest = prompt_manifest(operation, schema)
        manifest["model"] = self.settings.learning_answer_model
        manifest["retrieval_strategy"] = "protected_retrieval_v1"
        managed = None
        if operation == "generate" and "managed_prompt" in snapshot:
            from xuemian_ai.prompt_management.runtime import load_practice_prompt

            frozen = ManagedPromptSnapshot.model_validate(snapshot["managed_prompt"])
            if frozen.output_schema_sha256 != canonical_hash(schema):
                raise ValidationAppError(error_key="PROMPT_RUN_SNAPSHOT_INVALID")
            async with self.sessions() as session:
                managed = await load_practice_prompt(session, frozen, self.settings)
            # 保留旧manifest键，同时记录真正消费的版本；正文只留于调用栈内存。
            manifest.update(
                agent_key=frozen.agent_key,
                scene_key=frozen.scene_key,
                agent_run_id=str(frozen.agent_run_id),
                root_prompt_version_id=str(frozen.root_prompt_version_id),
                parts=[
                    {"key": p.definition_key, "version_id": str(p.version_id), "sha256": p.sha256}
                    for p in frozen.composition
                ],
                sha256=canonical_hash([p.sha256 for p in frozen.composition]),
                contract_sha256=frozen.contract_sha256,
                output_schema=frozen.output_schema_sha256,
                model=frozen.model,
                model_parameters=frozen.model_parameters,
            )

        async def resolve(state: ExecutionState) -> ExecutionState:
            await self.checkpoint(run, "resolving_context")
            if operation not in {"grade", "regrade"}:
                ensure_general_topic(config, snapshot.get("effective_context", {}))
            return {"config": config, "evidence": [], "trace_ids": []}

        async def retrieve(state: ExecutionState) -> ExecutionState:
            await self.checkpoint(run, "retrieving")
            if config.get("source_mode") != "materials" or operation in {"grade", "regrade"}:
                return {}
            evidence, traces = await self.retrieve(run, config)
            # Original source scope and versions remain fixed for the full operation.
            allowed = {
                (str(item["file_id"]), str(item["processing_version_id"]))
                for item in snapshot.get("source_snapshot", [])
            }
            if any((str(e.file_id), str(e.processing_version_id)) not in allowed for e in evidence):
                raise ValidationAppError("资料活动版本已改变", error_key="PRACTICE_SOURCE_CHANGED")
            if not evidence:
                raise ValidationAppError(
                    "资料中未找到充分出题依据", error_key="PRACTICE_EVIDENCE_INSUFFICIENT"
                )
            return {"evidence": evidence, "trace_ids": traces}

        async def generate(state: ExecutionState) -> ExecutionState:
            await self.checkpoint(
                run,
                "grading"
                if operation in {"grade", "regrade"}
                else "planning"
                if operation == "plan"
                else "generating",
            )
            payload: dict[str, Any] = {
                "config": config,
                "effective_context": snapshot.get("effective_context", {}),
                "evidence": [
                    {"number": i + 1, "content": e.content}
                    for i, e in enumerate(state.get("evidence", []))
                ],
                "question_schema": TypeAdapter(QuestionSnapshot).json_schema(),
                "grade_schema": GradePayload.model_json_schema(),
            }
            if operation in {"grade", "regrade"}:
                payload.update(question=snapshot["question"], answer=snapshot["answer"])
            if managed is not None:
                payload["_managed_prompt"] = managed.model_dump(mode="json")
            return {"raw": await self.provider.invoke(operation, payload)}

        async def validate(state: ExecutionState) -> ExecutionState:
            await self.checkpoint(run, "validating")
            raw = state["raw"]
            if operation in {"grade", "regrade"}:
                grade = validate_subjective_grade(
                    raw.get("grade", raw), snapshot["question"], snapshot["answer"]
                )
                return {"result": {"grade": grade.model_dump(mode="json")}}
            if operation == "plan":
                recommended = PracticeConfig.model_validate(raw["recommended_config"])
                candidate = recommended.model_dump(mode="json")
                for field in PROFILE_FIELDS:
                    if field not in recommended.model_fields_set:
                        candidate.pop(field, None)
                if any(
                    candidate.get(field) != config.get(field)
                    for field in ("source_mode", "knowledge_base_id", "file_ids", "mode")
                ):
                    raise UpstreamServiceError(error_key="PRACTICE_GENERATION_INVALID")
                for key in ("summary", "recommendation_summary"):
                    if not isinstance(raw.get(key), str) or not raw[key].strip():
                        raise UpstreamServiceError(error_key="PRACTICE_GENERATION_INVALID")
                return {
                    "result": {
                        "original_config": config,
                        "recommended_config": candidate,
                        "summary": raw["summary"],
                        "recommendation_summary": raw["recommendation_summary"],
                        "suggestions": raw.get("suggestions", []),
                        "effective_context": snapshot.get("effective_context", {}),
                    }
                }
            mapping = {
                str(item["file_id"]): str(item["file_asset_id"])
                for item in snapshot.get("source_snapshot", [])
            }
            questions = validate_questions(raw, config, state.get("evidence", []), mapping)
            if target:
                questions[0]["question_id"] = target["question_id"]
                questions = [
                    questions[0] if q["question_id"] == target["question_id"] else q
                    for q in snapshot["questions"]
                ]
                try:
                    questions = validate_question_snapshots(questions)
                except ValidationAppError:
                    raise UpstreamServiceError(error_key="PRACTICE_GENERATION_INVALID") from None
            return {
                "result": {
                    "questions": questions,
                    "source_snapshot": snapshot.get("source_snapshot", []),
                    "trace_ids": state.get("trace_ids", []),
                }
            }

        async def publish(state: ExecutionState) -> ExecutionState:
            await self.checkpoint(run, "publishing")
            assert run.lease_token is not None
            manifest["trace_ids"] = state.get("trace_ids", [])
            if not await self.repository.publish_run(
                run.id, run.lease_token, state["result"], manifest
            ):
                raise LeaseLost()
            return {}

        graph = StateGraph(ExecutionState)
        for name, node in (
            ("context", resolve),
            ("retrieval", retrieve),
            ("model", generate),
            ("validation", validate),
            ("publication", publish),
        ):
            graph.add_node(name, node)
        for before, after in (
            (START, "context"),
            ("context", "retrieval"),
            ("retrieval", "model"),
            ("model", "validation"),
            ("validation", "publication"),
            ("publication", END),
        ):
            graph.add_edge(before, after)
        await graph.compile().ainvoke({})

    async def heartbeat(
        self, run: ClaimedRun, task: asyncio.Task[None], failure: list[str]
    ) -> None:
        while True:
            await asyncio.sleep(self.settings.practice_worker_lease_seconds / 3)
            try:
                await self.checkpoint(run, "")
            except AppError as exc:
                failure.append(exc.error_key or "PRACTICE_NOT_FOUND")
                task.cancel()
                return
            except Exception:
                failure.append("PRACTICE_LEASE_INTERRUPTED")
                task.cancel()
                return

    async def run_once(self) -> bool:
        await self.repository.expire_runs()
        run = await self.repository.claim_run(
            self.worker_id, self.settings.practice_worker_lease_seconds
        )
        if run is None:
            return False
        if run.lease_token is None:
            return False
        run = RunClaim(
            run.id, run.owner_user_id, run.operation, run.input_snapshot, run.lease_token
        )
        bind_context(request_id=str(run.id))
        operation = asyncio.create_task(self.execute(run))
        pulse_failure: list[str] = []
        pulse = asyncio.create_task(self.heartbeat(run, operation, pulse_failure))
        try:
            async with asyncio.timeout(self.settings.practice_run_timeout_seconds):
                await operation
        except asyncio.CancelledError:
            error_key = pulse_failure[0] if pulse_failure else "PRACTICE_LEASE_INTERRUPTED"
            await self.fail(run, error_key, can_retry(error_key))
            current = asyncio.current_task()
            if current and current.cancelling():
                raise
        except LeaseLost:
            await self.fail(run, "PRACTICE_LEASE_INTERRUPTED", True)
        except TimeoutError:
            await self.fail(run, "PRACTICE_RUN_TIMEOUT", True)
        except AppError as exc:
            await self.fail(
                run,
                exc.error_key or "PRACTICE_GENERATION_INVALID",
                can_retry(exc.error_key or "PRACTICE_GENERATION_INVALID"),
            )
        except Exception:
            await self.fail(run, "PRACTICE_GENERATION_INVALID", True)
        finally:
            pulse.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pulse
        return True

    async def fail(self, run: ClaimedRun, error_key: str, retryable: bool) -> None:
        if run.lease_token is not None:
            await self.repository.fail_run(run.id, run.lease_token, error_key, retryable)
        _logger.warning("practice_run_failed", error_key=error_key)


async def serve() -> None:
    settings = get_settings()
    configure_logging(settings)
    infrastructure = Infrastructure.create(settings)
    store = VectorStore(settings)
    workers = [
        PracticeWorker(infrastructure.sessions, settings, store=store)
        for _ in range(settings.practice_worker_concurrency)
    ]

    async def loop(worker: PracticeWorker) -> None:
        while True:
            try:
                worked = await worker.run_once()
            except Exception:
                _logger.error(
                    "practice_worker_iteration_failed", error_key="PRACTICE_WORKER_UNAVAILABLE"
                )
                worked = False
            if not worked:
                await asyncio.sleep(settings.practice_worker_poll_seconds)

    try:
        await asyncio.gather(*(loop(worker) for worker in workers))
    finally:
        await store.close()
        await infrastructure.close()


def run() -> None:
    asyncio.run(serve())


def can_retry(error_key: str) -> bool:
    """Retry availability is explicit user action; the worker never requeues itself."""
    return error_key not in {
        "PRACTICE_SOURCE_CHANGED",
        "PRACTICE_VERSION_CONFLICT",
        "PRACTICE_PLAN_STALE",
        "PRACTICE_NOT_FOUND",
        "PRACTICE_EVIDENCE_INSUFFICIENT",
        "PRACTICE_CONFIG_INVALID",
    }
