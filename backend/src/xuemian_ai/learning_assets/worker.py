"""Durable knowledge generation and learning outbox execution with publication fencing."""

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol, TypedDict
from uuid import UUID, uuid4

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from xuemian_ai.core.config import Settings, get_settings
from xuemian_ai.core.errors import AppError, ValidationAppError
from xuemian_ai.core.logging import bind_context, configure_logging, get_logger
from xuemian_ai.document_processing.retrieval import RetrievalService
from xuemian_ai.document_processing.schemas import EvidenceChunk, RetrievalRequest
from xuemian_ai.document_processing.vector_store import VectorStore
from xuemian_ai.infrastructure.resources import Infrastructure
from xuemian_ai.learning_assets.generation import (
    EVIDENCE_CHARACTER_BUDGET,
    KnowledgeProvider,
    QwenKnowledgeProvider,
    audit_passages,
    audit_schema,
    fingerprint,
    prompt_manifest,
    validate_audit,
    validate_card,
)
from xuemian_ai.learning_assets.schemas import ExplanationConfig

_logger = get_logger(__name__)


@dataclass(frozen=True)
class RunClaim:
    id: UUID
    owner_user_id: UUID
    operation: str
    input_snapshot: dict[str, Any]
    lease_token: UUID


class RunRepository(Protocol):
    async def claim_run(self, worker_id: str) -> Any: ...
    async def heartbeat(self, run_id: UUID, token: UUID, stage: str) -> bool: ...
    async def publish_run(
        self,
        run_id: UUID,
        token: UUID,
        payload: dict[str, Any],
        manifest: dict[str, Any] | None = None,
    ) -> bool: ...
    async def fail_run(
        self, run_id: UUID, token: UUID, error_key: str, retryable: bool
    ) -> None: ...
    async def recover_expired(self) -> Any: ...


class EvidenceProjection(Protocol):
    async def process_next(self) -> bool: ...


class ExecutionState(TypedDict, total=False):
    evidence: list[EvidenceChunk]
    trace_ids: list[str]
    raw: dict[str, Any]
    result: dict[str, Any]


class LeaseLost(Exception):
    pass


class KnowledgeWorker:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
        provider: KnowledgeProvider | None = None,
        store: VectorStore | None = None,
        repository: RunRepository | None = None,
        projection: EvidenceProjection | None = None,
        retrieve: Callable[
            [RunClaim, dict[str, Any]], Awaitable[tuple[list[EvidenceChunk], list[str]]]
        ]
        | None = None,
    ) -> None:
        self.sessions, self.settings = sessions, settings
        self.provider = provider or QwenKnowledgeProvider(settings)
        self.store = store
        self.repository_override = repository is not None
        if repository is None:
            from xuemian_ai.learning_assets.service import LearningAssetService

            repository = LearningAssetService(sessions, UUID(int=0), settings)
        if projection is None:
            from xuemian_ai.learning_assets.projection import LearningProjection

            projection = LearningProjection(sessions)
        self.repository = repository
        self.projection = projection
        self.retrieve_override = retrieve
        self.worker_id = str(uuid4())

    def domain_repository(self, run: RunClaim) -> RunRepository:
        if self.repository_override:
            return self.repository
        from xuemian_ai.learning_assets.service import LearningAssetService

        return LearningAssetService(self.sessions, run.owner_user_id, self.settings)

    async def checkpoint(self, run: RunClaim, stage: str) -> None:
        if not await self.repository.heartbeat(run.id, run.lease_token, stage):
            raise LeaseLost()

    async def retrieve(
        self, run: RunClaim, config: dict[str, Any]
    ) -> tuple[list[EvidenceChunk], list[str]]:
        if self.retrieve_override:
            return await self.retrieve_override(run, config)
        service = RetrievalService(
            self.sessions, self.settings, run.owner_user_id, str(run.id), vector_store=self.store
        )
        snapshot = run.input_snapshot.get("source_snapshot", [])
        if not snapshot:
            raise ValidationAppError(error_key="KNOWLEDGE_EVIDENCE_INSUFFICIENT")
        try:
            result = await service.search(
                UUID(config["knowledge_base_id"]),
                RetrievalRequest(
                    query=config["topic"],
                    file_ids=[UUID(source["file_id"]) for source in snapshot],
                    top_n=8,
                ),
            )
            if not result.trace_complete:
                raise ValidationAppError(error_key="KNOWLEDGE_RETRIEVAL_INCOMPLETE")
            return result.evidence, [str(result.trace_id)]
        finally:
            if service.owns_store:
                await service.vector_store.close()

    async def execute(self, run: RunClaim) -> None:
        snapshot = run.input_snapshot
        config = ExplanationConfig.model_validate(snapshot["config"]).model_dump(mode="json")
        if not config["topic"].strip():
            raise ValidationAppError(error_key="KNOWLEDGE_CONFIG_INVALID")
        manifest = prompt_manifest(run.operation)
        manifest["model"] = self.settings.learning_answer_model
        manifest["retrieval_strategy"] = "protected_retrieval_v1"

        async def resolve(state: ExecutionState) -> ExecutionState:
            await self.checkpoint(run, "resolving_context")
            return {"evidence": [], "trace_ids": []}

        async def retrieve(state: ExecutionState) -> ExecutionState:
            await self.checkpoint(run, "retrieving")
            if config["source_mode"] == "general":
                return {}
            evidence, traces = await self.retrieve(run, config)
            allowed = {
                (str(source["file_id"]), str(source["processing_version_id"]))
                for source in snapshot.get("source_snapshot", [])
            }
            if any((str(e.file_id), str(e.processing_version_id)) not in allowed for e in evidence):
                raise ValidationAppError(error_key="LEARNING_ASSET_SOURCE_CHANGED")
            if not evidence:
                raise ValidationAppError(error_key="KNOWLEDGE_EVIDENCE_INSUFFICIENT")
            if not traces:
                raise ValidationAppError(error_key="KNOWLEDGE_RETRIEVAL_INCOMPLETE")
            if sum(len(e.content) for e in evidence) > EVIDENCE_CHARACTER_BUDGET:
                raise ValidationAppError(error_key="KNOWLEDGE_CONTEXT_TOO_LARGE")
            return {"evidence": evidence, "trace_ids": traces}

        async def generate(state: ExecutionState) -> ExecutionState:
            await self.checkpoint(run, "generating")
            return {
                "raw": await self.provider.invoke(
                    run.operation,
                    {
                        "config": config,
                        "effective_context": snapshot.get("effective_context", {}),
                        "evidence": [
                            {"number": i + 1, "content": e.content}
                            for i, e in enumerate(state.get("evidence", []))
                        ],
                    },
                )
            }

        async def validate(state: ExecutionState) -> ExecutionState:
            await self.checkpoint(run, "validating")
            mapping = {
                str(source["file_id"]): str(source["file_asset_id"])
                for source in snapshot.get("source_snapshot", [])
            }
            result = validate_card(state["raw"], config["source_mode"], state["evidence"], mapping)
            if config["source_mode"] == "materials":
                passages = audit_passages(result)
                audit_payload = {
                    "passages": passages,
                    "evidence": [
                        {"number": i + 1, "content": e.content}
                        for i, e in enumerate(state["evidence"])
                    ],
                }
                reviewed = await self.provider.invoke("audit", audit_payload)
                validate_audit(reviewed, passages, state["evidence"])
                manifest["grounding_audit"] = prompt_manifest("audit")
                manifest["grounding_audit"]["output_schema"] = fingerprint(
                    json.dumps(audit_schema(audit_payload), sort_keys=True)
                )
            return {"result": result.model_dump(mode="json")}

        async def publish(state: ExecutionState) -> ExecutionState:
            await self.checkpoint(run, "publishing")
            manifest["trace_ids"] = state["trace_ids"]
            if not await self.domain_repository(run).publish_run(
                run.id, run.lease_token, state["result"], manifest
            ):
                raise LeaseLost()
            return {}

        graph = StateGraph(ExecutionState)
        nodes = [
            ("context", resolve),
            ("retrieval", retrieve),
            ("model", generate),
            ("validation", validate),
            ("publication", publish),
        ]
        for name, node in nodes:
            graph.add_node(name, node)
        path = [START, *(name for name, _ in nodes), END]
        for before, after in zip(path, path[1:], strict=False):
            graph.add_edge(before, after)
        await graph.compile().ainvoke({})

    async def heartbeat(self, run: RunClaim, task: asyncio.Task[None], failure: list[str]) -> None:
        while True:
            await asyncio.sleep(self.settings.knowledge_worker_lease_seconds / 3)
            try:
                await self.checkpoint(run, "")
            except AppError as exc:
                failure.append(exc.error_key or "LEARNING_ASSET_NOT_FOUND")
                task.cancel()
                return
            except Exception:
                failure.append("KNOWLEDGE_LEASE_INTERRUPTED")
                task.cancel()
                return

    async def run_once(self) -> bool:
        await self.repository.recover_expired()
        projected = await self.projection.process_next()
        item = await self.repository.claim_run(self.worker_id)
        if item is None or item.lease_token is None:
            return projected
        run = RunClaim(
            item.id,
            item.owner_user_id,
            item.operation,
            deepcopy(item.input_snapshot),
            item.lease_token,
        )
        bind_context(request_id=str(run.id))
        operation = asyncio.create_task(self.execute(run))
        pulse_failure: list[str] = []
        pulse = asyncio.create_task(self.heartbeat(run, operation, pulse_failure))
        try:
            async with asyncio.timeout(self.settings.knowledge_run_timeout_seconds):
                await operation
        except asyncio.CancelledError:
            error_key = pulse_failure[0] if pulse_failure else "KNOWLEDGE_LEASE_INTERRUPTED"
            await self.fail(run, error_key, can_retry(error_key))
            current = asyncio.current_task()
            if current and current.cancelling():
                raise
        except LeaseLost:
            await self.fail(run, "KNOWLEDGE_LEASE_INTERRUPTED", True)
        except TimeoutError:
            await self.fail(run, "KNOWLEDGE_RUN_TIMEOUT", True)
        except AppError as exc:
            key = exc.error_key or "KNOWLEDGE_OUTPUT_INVALID"
            await self.fail(run, key, can_retry(key))
        except Exception:
            await self.fail(run, "KNOWLEDGE_OUTPUT_INVALID", True)
        finally:
            pulse.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pulse
        return True

    async def fail(self, run: RunClaim, error_key: str, retryable: bool) -> None:
        await self.domain_repository(run).fail_run(run.id, run.lease_token, error_key, retryable)
        _logger.warning("knowledge_run_failed", run_id=str(run.id), error_key=error_key)


def can_retry(error_key: str) -> bool:
    return error_key not in {
        "LEARNING_ASSET_SOURCE_CHANGED",
        "LEARNING_ASSET_NOT_FOUND",
        "LEARNING_ASSET_VERSION_CONFLICT",
        "KNOWLEDGE_EVIDENCE_INSUFFICIENT",
        "KNOWLEDGE_CONFIG_INVALID",
        "KNOWLEDGE_CONTEXT_TOO_LARGE",
    }


async def serve() -> None:
    settings = get_settings()
    configure_logging(settings)
    infrastructure = Infrastructure.create(settings)
    store = VectorStore(settings)
    workers = [
        KnowledgeWorker(infrastructure.sessions, settings, store=store)
        for _ in range(settings.knowledge_worker_concurrency)
    ]

    async def loop(worker: KnowledgeWorker) -> None:
        while True:
            try:
                worked = await worker.run_once()
            except Exception:
                _logger.error(
                    "knowledge_worker_iteration_failed", error_key="KNOWLEDGE_WORKER_UNAVAILABLE"
                )
                worked = False
            if not worked:
                await asyncio.sleep(settings.knowledge_worker_poll_seconds)

    try:
        await asyncio.gather(*(loop(worker) for worker in workers))
    finally:
        await store.close()
        await infrastructure.close()


def run() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    run()
