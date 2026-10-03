"""真实业务队列消费已冻结版本，发布/停用和重试不得让旧任务漂移。"""

import os
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_practice_http_integration import SyntheticProvider
from test_prompt_integration import seed_published

from xuemian_ai.accounts.models import User
from xuemian_ai.agent_runs.models import AgentRun
from xuemian_ai.core.errors import UpstreamServiceError
from xuemian_ai.practice.models import PracticeRun
from xuemian_ai.practice.schemas import (
    GenerateRequest,
    PlanRequest,
    PracticeConfig,
    RetryRequest,
    SetCreate,
)
from xuemian_ai.practice.worker import PracticeWorker
from xuemian_ai.prompt_management.schemas import StatusRequest
from xuemian_ai.prompt_management.service import PromptService

pytest_plugins = ["test_practice_domain_integration"]
pytestmark = pytest.mark.skipif(
    not os.getenv("PRACTICE_INTEGRATION_DB"), reason="explicit isolated database required"
)


async def enqueue(domain):
    config = PracticeConfig(topic="合成事务", question_count=1, question_types={"single_choice": 1})
    obj = await domain.create(SetCreate(config=config, request_key=uuid4()))
    plan = await domain.plan(obj.id, PlanRequest(expected_version=obj.version, request_key=uuid4()))
    claim = await domain.claim_run("managed-plan")
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
    proposal = await domain.get_plan(obj.id, (await domain.get_run(plan.id)).result_ref.version)
    run = await domain.generate(
        obj.id,
        GenerateRequest(
            expected_version=obj.version,
            plan_version=proposal.version,
            candidate="original",
            confirmed_config_digest=proposal.original.config_digest,
            request_key=uuid4(),
        ),
    )
    return run


async def metadata(domain, run_id):
    async with domain.sessions() as session:
        return await session.scalar(select(AgentRun).where(AgentRun.practice_run_id == run_id))


class RecordingProvider(SyntheticProvider):
    managed = None

    async def invoke(self, operation, payload):
        self.managed = payload.get("_managed_prompt")
        return await super().invoke(operation, payload)


async def test_real_worker_consumes_old_version_after_new_publication_and_disable(domain):
    run = await enqueue(domain)
    before = await metadata(domain, run.id)
    assert before.status == "pending" and before.output_reference is None
    async with domain.sessions() as session:
        admin = await session.scalar(
            select(User).where(User.role == "admin", User.username.like("managed%"))
        )
    prompts = PromptService(domain.sessions, admin.id, domain.settings)
    definition, replacement = await seed_published(prompts)
    assert replacement.id != before.root_prompt_version_id
    await prompts.status(
        definition.id,
        StatusRequest(expected_active_version_id=replacement.id, runtime_status="disabled"),
    )
    provider = RecordingProvider()
    worker = PracticeWorker(
        domain.sessions,
        domain.settings.model_copy(update={"learning_answer_model": "changed-after-enqueue"}),
        provider=provider,
    )
    assert await worker.run_once()
    result = await domain.get_run(run.id)
    after = await metadata(domain, run.id)
    assert result.status == after.status == "succeeded"
    assert (
        after.snapshot == before.snapshot
        and after.root_prompt_version_id == before.root_prompt_version_id
    )
    assert after.output_reference == result.result_ref.model_dump(mode="json")
    assert provider.managed["snapshot"]["model"] == before.snapshot["model"]
    async with domain.sessions() as session:
        persisted = await session.get(PracticeRun, run.id)
        assert persisted.manifest["root_prompt_version_id"] == str(before.root_prompt_version_id)
    # 运行和审计元数据仅保存引用；题目和装配后的正文由原领域/调用栈负责。
    assert "system_messages" not in str(after.snapshot) and "全部成功或全部回滚" not in str(
        after.output_reference
    )
    # 停用只拦截新的入队，事务失败不能留下无快照的业务任务。
    with pytest.raises(UpstreamServiceError) as unavailable:
        await enqueue(domain)
    assert unavailable.value.error_key == "PROMPT_RUNTIME_UNAVAILABLE"
    async with domain.sessions() as session:
        managed_runs = (
            await session.scalars(select(AgentRun).where(AgentRun.owner_user_id == domain.owner))
        ).all()
        assert len(managed_runs) == 1


async def test_managed_retry_preserves_snapshot_and_cancel_updates_agent_run(domain):
    run = await enqueue(domain)
    before = await metadata(domain, run.id)
    claim = await domain.claim_run("managed-failure")
    assert claim.id == run.id and (await metadata(domain, run.id)).status == "processing"
    assert await domain.fail_run(run.id, claim.lease_token, "PRACTICE_PROVIDER_UNAVAILABLE", True)
    failed = await metadata(domain, run.id)
    assert failed.status == "failed" and failed.error_key == "PRACTICE_PROVIDER_UNAVAILABLE"
    await domain.retry(
        run.id, RetryRequest(request_key=run.request_key, input_digest=run.input_digest)
    )
    retried = await metadata(domain, run.id)
    assert (
        retried.status == "pending"
        and retried.snapshot == before.snapshot
        and retried.id == before.id
    )
    await domain.cancel(run.id)
    assert (await metadata(domain, run.id)).status == "cancelled"
    async with domain.sessions() as session:
        persisted = await session.get(PracticeRun, run.id)
        assert persisted.input_snapshot["managed_prompt"] == before.snapshot
