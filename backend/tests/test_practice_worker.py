import asyncio
from types import SimpleNamespace
from uuid import uuid4

from test_practice_generation import config, evidence, question

from xuemian_ai.practice.worker import PracticeWorker


class Repository:
    def __init__(self, operation="generate", payload=None):
        self.item = SimpleNamespace(
            id=uuid4(),
            owner_user_id=uuid4(),
            operation=operation,
            lease_token=uuid4(),
            input_snapshot=payload
            or {
                "config": dict(config(), topic="SQL"),
                "effective_context": {},
                "source_snapshot": [],
            },
        )
        self.status = "pending"
        self.published = None
        self.stages = []
        self.error_key = None
        self.retryable = False
        self.expire_calls = 0

    async def claim_run(self, worker_id, lease_seconds):
        if self.status != "pending":
            return None
        self.status = "processing"
        return self.item

    async def heartbeat(self, run_id, token, lease_seconds, stage):
        if self.status != "processing" or token != self.item.lease_token:
            return False
        if stage:
            self.stages.append(stage)
        return True

    async def publish_run(self, run_id, token, result, manifest):
        if self.status != "processing" or token != self.item.lease_token:
            return False
        self.published = result
        self.manifest = manifest
        self.status = "succeeded"
        return True

    async def fail_run(self, run_id, token, error_key, retryable):
        if token != self.item.lease_token:
            return False
        self.status = "cancelled" if self.status == "cancel_requested" else "failed"
        self.error_key = error_key
        self.retryable = retryable
        return True

    async def expire_runs(self):
        self.expire_calls += 1


class Provider:
    def __init__(self, result=None, callback=None):
        self.result = result or {"status": "ready", "questions": [question()]}
        self.callback = callback
        self.calls = 0

    async def invoke(self, operation, payload):
        self.calls += 1
        self.payload = payload
        if self.callback:
            await self.callback()
        return self.result


async def test_plan_keeps_omitted_profile_fields_absent_and_explicit_clear():
    repo = Repository("plan")
    repo.item.input_snapshot["config"].update(mode="practice", file_ids=[], knowledge_base_id=None)
    candidate = dict(repo.item.input_snapshot["config"], target_job=None)
    result = {
        "recommended_config": candidate,
        "summary": "原配置",
        "recommendation_summary": "推荐配置",
    }
    await worker(repo, Provider(result)).run_once()
    assert repo.status == "succeeded"
    published = repo.published["recommended_config"]
    assert published["target_job"] is None
    assert "experience_months" not in published
    assert "target_skills" not in published


async def test_knowledge_base_retrieval_uses_fixed_snapshot_files():
    from unittest.mock import AsyncMock, patch

    repo = Repository()
    source = evidence()
    repo.item.input_snapshot["source_snapshot"] = [
        {"file_id": str(source.file_id), "processing_version_id": str(source.processing_version_id)}
    ]
    w = worker(repo)
    with patch("xuemian_ai.practice.worker.RetrievalService") as retrieval:
        service = retrieval.return_value
        service.search = AsyncMock(
            return_value=SimpleNamespace(evidence=[source], trace_id=uuid4())
        )
        service.owns_store = False
        await w.retrieve(
            repo.item,
            dict(
                config(mode="materials"), knowledge_base_id=str(uuid4()), file_ids=[], topic="SQL"
            ),
        )
        request = service.search.call_args.args[1]
        assert request.file_ids == [source.file_id]


def worker(repo, provider=None, retrieve=None, timeout=2):
    settings = SimpleNamespace(
        practice_worker_lease_seconds=0.03,
        practice_run_timeout_seconds=timeout,
        learning_answer_model="qwen3.8-flash",
    )
    return PracticeWorker(
        None, settings, repository=repo, provider=provider or Provider(), retrieve=retrieve
    )


async def test_real_graph_stages_and_manifest_publish():
    repo = Repository()
    assert await worker(repo).run_once()
    assert repo.status == "succeeded"
    assert repo.stages == [
        "resolving_context",
        "retrieving",
        "generating",
        "validating",
        "publishing",
    ]
    assert repo.manifest["model"] == "qwen3.8-flash"
    assert repo.expire_calls == 1
    assert not await worker(repo).run_once()


async def test_cancel_after_model_drops_unpublished_result():
    repo = Repository()

    async def cancel():
        repo.status = "cancel_requested"

    await worker(repo, Provider(callback=cancel)).run_once()
    assert repo.status == "cancelled"
    assert repo.published is None


async def test_lease_token_fences_late_model_return():
    repo = Repository()

    async def revoke():
        repo.status = "failed"
        repo.item.lease_token = uuid4()

    await worker(repo, Provider(callback=revoke)).run_once()
    assert repo.published is None


async def test_timeout_is_bounded_and_explicitly_retryable():
    repo = Repository()

    async def block():
        await asyncio.sleep(10)

    await worker(repo, Provider(callback=block), timeout=0.01).run_once()
    assert repo.status == "failed"
    assert repo.error_key == "PRACTICE_RUN_TIMEOUT"
    assert repo.retryable
    assert repo.published is None


async def test_invalid_result_is_not_automatically_retried():
    repo = Repository()
    provider = Provider({"status": "ready", "questions": []})
    await worker(repo, provider).run_once()
    assert repo.status == "failed"
    assert repo.retryable  # Only an explicit user retry may requeue this run.
    assert provider.calls == 1


async def test_materials_empty_skips_provider():
    repo = Repository(
        payload={
            "config": dict(config(mode="materials"), topic="SQL"),
            "effective_context": {},
            "source_snapshot": [],
        }
    )
    provider = Provider()

    async def retrieve(run, config):
        return [], []

    await worker(repo, provider, retrieve).run_once()
    assert repo.error_key == "PRACTICE_EVIDENCE_INSUFFICIENT"
    assert provider.calls == 0


async def test_source_version_changed_rejects_before_provider():
    repo = Repository(
        payload={
            "config": dict(config(mode="materials"), topic="SQL"),
            "effective_context": {},
            "source_snapshot": [],
        }
    )
    provider = Provider()

    async def retrieve(run, config):
        return [evidence()], [str(uuid4())]

    await worker(repo, provider, retrieve).run_once()
    assert repo.error_key == "PRACTICE_SOURCE_CHANGED"
    assert provider.calls == 0


async def test_single_regeneration_preserves_other_questions_and_identity():
    first, second = question(), question("true_false")
    second["stem"] = "事务具有原子性吗？"
    first.pop("citation_ids")
    second.pop("citation_ids")
    first["source_refs"] = []
    second["source_refs"] = []
    repo = Repository(
        "regenerate",
        {
            "config": dict(config(), topic="SQL"),
            "questions": [first, second],
            "question_id": second["question_id"],
            "source_snapshot": [],
        },
    )
    new = question("true_false")
    new["stem"] = "事务操作能否拆分提交？"
    await worker(repo, Provider({"status": "ready", "questions": [new]})).run_once()
    assert repo.status == "succeeded"
    assert repo.published["questions"][0] == first
    assert repo.published["questions"][1]["question_id"] == second["question_id"]


async def test_plan_cannot_change_source_scope():
    repo = Repository("plan")
    await worker(
        repo,
        Provider(
            {
                "recommended_config": dict(
                    config(mode="materials"), knowledge_base_id=str(uuid4())
                ),
                "summary": "SQL",
                "recommendation_summary": "SQL",
            }
        ),
    ).run_once()
    assert repo.status == "failed"
    assert repo.published is None


async def test_source_revoked_during_model_wait_retains_specific_failure():
    from xuemian_ai.core.errors import ConflictError

    repo = Repository()
    old = repo.heartbeat
    model_started = False

    async def heartbeat(run_id, token, lease_seconds, stage):
        if model_started and not stage:
            raise ConflictError(error_key="PRACTICE_SOURCE_CHANGED")
        return await old(run_id, token, lease_seconds, stage)

    async def block():
        nonlocal model_started
        model_started = True
        await asyncio.sleep(10)

    repo.heartbeat = heartbeat
    await worker(repo, Provider(callback=block)).run_once()
    assert repo.error_key == "PRACTICE_SOURCE_CHANGED"
    assert not repo.retryable
    assert repo.published is None


async def test_material_graph_maps_binding_id_to_asset_and_records_trace():
    item = evidence()
    asset = uuid4()
    trace = str(uuid4())
    repo = Repository(
        payload={
            "config": dict(config(mode="materials"), topic="SQL"),
            "effective_context": {},
            "source_snapshot": [
                {
                    "file_id": str(item.file_id),
                    "file_asset_id": str(asset),
                    "processing_version_id": str(item.processing_version_id),
                }
            ],
        }
    )
    q = question()
    q["citation_ids"] = [1]

    async def retrieve(run, config):
        return [item], [trace]

    await worker(repo, Provider({"status": "ready", "questions": [q]}), retrieve).run_once()
    assert repo.status == "succeeded"
    ref = repo.published["questions"][0]["source_refs"][0]
    assert ref["file_id"] == str(item.file_id)
    assert ref["file_asset_id"] == str(asset)
    assert repo.manifest["trace_ids"] == [trace]
