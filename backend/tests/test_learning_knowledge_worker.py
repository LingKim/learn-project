import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from test_learning_knowledge_generation import card
from test_practice_generation import evidence

from xuemian_ai.core.errors import ConflictError
from xuemian_ai.learning_assets.generation import EVIDENCE_CHARACTER_BUDGET
from xuemian_ai.learning_assets.worker import KnowledgeWorker


class Repository:
    def __init__(self):
        self.item = SimpleNamespace(
            id=uuid4(),
            owner_user_id=uuid4(),
            operation="generate",
            lease_token=uuid4(),
            input_snapshot={
                "config": {"topic": "事务", "source_mode": "general"},
                "effective_context": {},
                "source_snapshot": [],
            },
        )
        self.status = "pending"
        self.published = None
        self.stages = []
        self.error_key = None
        self.retryable = False
        self.recover_calls = 0

    async def claim_run(self, worker_id):
        if self.status != "pending":
            return None
        self.status = "processing"
        return self.item

    async def heartbeat(self, run_id, token, stage):
        if self.status != "processing" or token != self.item.lease_token:
            return False
        if stage:
            self.stages.append(stage)
        return True

    async def publish_run(self, run_id, token, payload, manifest=None):
        if self.status != "processing" or token != self.item.lease_token:
            return False
        self.status = "succeeded"
        self.published = payload
        self.manifest = manifest
        return True

    async def fail_run(self, run_id, token, error_key, retryable):
        if self.item.lease_token != token:
            return False
        self.status = "cancelled" if self.status == "cancel_requested" else "failed"
        self.error_key = error_key
        self.retryable = retryable
        return True

    async def recover_expired(self):
        self.recover_calls += 1


class Projection:
    def __init__(self, worked=False):
        self.calls = 0
        self.worked = worked

    async def process_next(self):
        self.calls += 1
        return self.worked


class Provider:
    def __init__(self, result=None, callback=None):
        self.result = result or card()
        self.callback = callback
        self.calls = 0
        self.audit_result = None

    async def invoke(self, operation, payload):
        self.calls += 1
        if operation == "audit":
            if self.audit_result is not None:
                return self.audit_result
            return {
                name: {
                    "status": "supported",
                    "reason": "合成测试：对应给定资料事实",
                    "evidence": [{"evidence_id": 1, "quote": payload["evidence"][0]["content"]}],
                }
                for name in payload["passages"]
            }
        self.payload = payload
        if self.callback:
            await self.callback()
        return self.result


def worker(repo, provider=None, retrieve=None, projection=None, timeout=2):
    return KnowledgeWorker(
        None,
        SimpleNamespace(
            knowledge_worker_lease_seconds=0.03,
            knowledge_run_timeout_seconds=timeout,
            learning_answer_model="qwen3.8-flash",
        ),
        repository=repo,
        provider=provider or Provider(),
        retrieve=retrieve,
        projection=projection or Projection(),
    )


def materials(repo, source):
    repo.item.input_snapshot["config"].update(
        source_mode="materials", knowledge_base_id=str(uuid4())
    )
    repo.item.input_snapshot["source_snapshot"] = [
        {
            "file_id": str(source.file_id),
            "file_asset_id": str(uuid4()),
            "processing_version_id": str(source.processing_version_id),
        }
    ]


async def test_real_graph_consumes_outbox_and_publishes_manifest():
    repo, projection = Repository(), Projection()
    w = worker(repo, projection=projection)
    assert await w.run_once()
    assert repo.status == "succeeded"
    assert repo.stages == [
        "resolving_context",
        "retrieving",
        "generating",
        "validating",
        "publishing",
    ]
    assert repo.published["source_mode"] == "general"
    assert repo.manifest["model"] == "qwen3.8-flash"
    assert repo.manifest["trace_ids"] == []
    assert repo.recover_calls == 1
    assert projection.calls == 1
    assert not await w.run_once()
    assert projection.calls == 2


async def test_outbox_without_generation_is_reported_as_work():
    repo = Repository()
    repo.status = "succeeded"
    assert await worker(repo, projection=Projection(True)).run_once()


async def test_materials_scope_and_trace_persist_without_prompt_or_source_text():
    repo, source = Repository(), evidence()
    materials(repo, source)
    trace = str(uuid4())

    async def retrieve(run, config):
        return [source], [trace]

    provider = Provider(card([1]))
    await worker(repo, provider, retrieve).run_once()
    assert repo.status == "succeeded"
    assert repo.manifest["trace_ids"] == [trace]
    assert provider.payload["evidence"] == [{"number": 1, "content": source.content}]
    assert (
        repo.published["citations"][0]["file_asset_id"]
        == repo.item.input_snapshot["source_snapshot"][0]["file_asset_id"]
    )
    assert "content" not in repo.published["citations"][0]
    assert "prompt" not in repo.manifest


async def test_retrieval_uses_snapshot_files_and_requires_complete_trace():
    repo, source = Repository(), evidence()
    materials(repo, source)
    w = worker(repo)
    with patch("xuemian_ai.learning_assets.worker.RetrievalService") as retrieval:
        service = retrieval.return_value
        service.owns_store = False
        service.search = AsyncMock(
            return_value=SimpleNamespace(evidence=[source], trace_complete=True, trace_id=uuid4())
        )
        await w.retrieve(repo.item, repo.item.input_snapshot["config"])
        assert service.search.call_args.args[1].file_ids == [source.file_id]
        service.search.return_value.trace_complete = False
        await w.run_once()
        assert repo.error_key == "KNOWLEDGE_RETRIEVAL_INCOMPLETE"
        assert repo.published is None


async def test_empty_materials_do_not_call_model_or_fall_back_to_general():
    repo, provider = Repository(), Provider()
    materials(repo, evidence())

    async def retrieve(run, config):
        return [], [str(uuid4())]

    await worker(repo, provider, retrieve).run_once()
    assert repo.error_key == "KNOWLEDGE_EVIDENCE_INSUFFICIENT"
    assert not repo.retryable
    assert provider.calls == 0


async def test_changed_sources_are_rejected_before_model():
    repo, provider = Repository(), Provider()
    materials(repo, evidence())

    async def retrieve(run, config):
        return [evidence()], [str(uuid4())]

    await worker(repo, provider, retrieve).run_once()
    assert repo.error_key == "LEARNING_ASSET_SOURCE_CHANGED"
    assert provider.calls == 0


async def test_oversized_evidence_rejects_instead_of_truncating():
    repo, source, provider = Repository(), evidence(), Provider()
    source.content = "甲" * (EVIDENCE_CHARACTER_BUDGET + 1)
    materials(repo, source)

    async def retrieve(run, config):
        return [source], [str(uuid4())]

    await worker(repo, provider, retrieve).run_once()
    assert repo.error_key == "KNOWLEDGE_CONTEXT_TOO_LARGE"
    assert not repo.retryable
    assert provider.calls == 0


async def test_cancel_after_model_return_drops_result():
    repo = Repository()

    async def cancel():
        repo.status = "cancel_requested"

    await worker(repo, Provider(callback=cancel)).run_once()
    assert repo.status == "cancelled"
    assert repo.published is None


async def test_lease_token_rotation_fences_late_return():
    repo = Repository()

    async def rotate():
        repo.item.lease_token = uuid4()

    await worker(repo, Provider(callback=rotate)).run_once()
    assert repo.published is None
    assert repo.error_key is None


async def test_timeout_is_bounded_with_explicit_retry_only():
    repo = Repository()

    async def block():
        await asyncio.sleep(10)

    provider = Provider(callback=block)
    await worker(repo, provider, timeout=0.01).run_once()
    assert repo.error_key == "KNOWLEDGE_RUN_TIMEOUT"
    assert repo.retryable
    assert provider.calls == 1
    assert repo.published is None


async def test_source_revocation_during_model_heartbeat_keeps_specific_error():
    repo = Repository()
    original = repo.heartbeat
    model_started = False

    async def heartbeat(run_id, token, stage):
        if model_started and not stage:
            raise ConflictError(error_key="LEARNING_ASSET_SOURCE_CHANGED")
        return await original(run_id, token, stage)

    async def block():
        nonlocal model_started
        model_started = True
        await asyncio.sleep(10)

    repo.heartbeat = heartbeat
    await worker(repo, Provider(callback=block)).run_once()
    assert repo.error_key == "LEARNING_ASSET_SOURCE_CHANGED"
    assert not repo.retryable
    assert repo.published is None


async def test_invalid_model_result_retains_no_published_card():
    repo = Repository()
    await worker(repo, Provider({"status": "ready", "reason": "", "card": None})).run_once()
    assert repo.error_key == "KNOWLEDGE_OUTPUT_INVALID"
    assert repo.retryable
    assert repo.published is None


async def test_source_fence_in_publication_preserves_specific_nonretryable_failure():
    repo = Repository()

    async def reject(run_id, token, payload, manifest=None):
        raise ConflictError(error_key="LEARNING_ASSET_SOURCE_CHANGED")

    repo.publish_run = reject
    await worker(repo).run_once()
    assert repo.published is None
    assert repo.error_key == "LEARNING_ASSET_SOURCE_CHANGED"
    assert not repo.retryable


async def test_default_service_publishes_using_claim_owner():
    repo = Repository()
    owners = []

    def service_factory(sessions, owner, settings):
        owners.append(owner)
        return repo

    with patch(
        "xuemian_ai.learning_assets.service.LearningAssetService", side_effect=service_factory
    ):
        w = KnowledgeWorker(
            None,
            SimpleNamespace(
                knowledge_worker_lease_seconds=0.03,
                knowledge_run_timeout_seconds=2,
                learning_answer_model="qwen3.8-flash",
            ),
            provider=Provider(),
            projection=Projection(),
        )
        await w.run_once()
    assert owners[0].int == 0
    assert owners[1] == repo.item.owner_user_id
    assert repo.status == "succeeded"


async def test_unsupported_audit_drops_material_card_without_rewriting():
    repo, source, provider = Repository(), evidence(), Provider(card([1]))
    materials(repo, source)
    provider.audit_result = {
        "concept": {"status": "unsupported", "reason": "资料没有支持新增保证", "evidence": []}
    }

    async def retrieve(run, config):
        return [source], [str(uuid4())]

    await worker(repo, provider, retrieve).run_once()
    assert repo.error_key == "KNOWLEDGE_OUTPUT_INVALID"
    assert repo.published is None
    assert provider.calls == 2


async def test_audit_provider_failure_drops_material_card():
    from xuemian_ai.core.errors import UpstreamServiceError

    repo, source, provider = Repository(), evidence(), Provider(card([1]))
    materials(repo, source)
    invoke = provider.invoke

    async def fail_audit(operation, payload):
        if operation == "audit":
            raise UpstreamServiceError(error_key="KNOWLEDGE_PROVIDER_UNAVAILABLE")
        return await invoke(operation, payload)

    async def retrieve(run, config):
        return [source], [str(uuid4())]

    provider.invoke = fail_audit
    await worker(repo, provider, retrieve).run_once()
    assert repo.error_key == "KNOWLEDGE_PROVIDER_UNAVAILABLE"
    assert repo.published is None


async def test_successful_material_audit_manifest_excludes_review_content():
    repo, source, provider = Repository(), evidence(), Provider(card([1]))
    materials(repo, source)

    async def retrieve(run, config):
        return [source], [str(uuid4())]

    await worker(repo, provider, retrieve).run_once()
    assert repo.status == "succeeded"
    assert repo.manifest["grounding_audit"]["scene_key"] == "knowledge_audit"
    assert "quote" not in str(repo.manifest)
    assert "合成测试对应" not in str(repo.manifest)
    assert provider.calls == 2
