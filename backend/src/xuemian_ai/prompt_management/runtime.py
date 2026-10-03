"""入队固定依赖、代码契约和模型参数；执行时只验证不可变快照，不重新选活动版本。"""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xuemian_ai.agent_runs.contracts import (
    ContextSourceSnapshot,
    ManagedPromptSnapshot,
    PromptPartSnapshot,
    RenderedManagedPrompt,
    canonical_hash,
)
from xuemian_ai.agent_runs.models import AgentRun
from xuemian_ai.core.errors import UpstreamServiceError
from xuemian_ai.core.status_codes import ApiStatusCode
from xuemian_ai.practice.models import PracticeRun
from xuemian_ai.prompt_management.models import (
    PromptDefinition,
    PromptVersion,
    PromptVersionDependency,
)
from xuemian_ai.prompt_management.registry import CONTRACT_SHA256, ROOT_KEY, model_configuration
from xuemian_ai.prompt_management.rendering import render
from xuemian_ai.prompt_management.schemas import Variable
from xuemian_ai.prompt_management.service import PromptService, content_hash


def unavailable() -> UpstreamServiceError:
    return UpstreamServiceError(
        "受管出题提示词暂不可用",
        status_code=ApiStatusCode.SERVICE_UNAVAILABLE,
        error_key="PROMPT_RUNTIME_UNAVAILABLE",
    )


def context_sources(data: dict[str, Any]) -> list[ContextSourceSnapshot]:
    context = data.get("effective_context") or {}
    values, supplied = context.get("values", {}), context.get("sources", {})
    mapping = {
        "explicit": "request",
        "request": "request",
        "materials": "selected_asset",
        "learning_asset": "selected_asset",
        "selected_asset": "selected_asset",
        "weakness": "weakness",
        "profile": "profile",
        "default": "default",
    }
    result = []
    for field, value in values.items():
        if field not in {
            "target_job",
            "experience_months",
            "target_level",
            "target_skills",
            "focus_topics",
            "learning_goal",
            "preferred_language",
        }:
            continue
        source = mapping.get(supplied.get(field, "default"))
        if source is None:
            raise unavailable()
        target = context.get("learning_target") or {}
        if source == "selected_asset" and target.get("kind") == "weakness":
            source = "weakness"
        reference_id = (
            UUID(str(target["id"]))
            if source in {"selected_asset", "weakness"} and target.get("id")
            else None
        )
        reference_version = (
            target.get("version", target.get("card_version"))
            if reference_id
            else context.get("profile_version")
            if source == "profile"
            else None
        )
        result.append(
            ContextSourceSnapshot.model_validate(
                {
                    "field": field,
                    "source": source,
                    "digest": canonical_hash(value),
                    "reference_id": reference_id,
                    "reference_version": str(reference_version)
                    if reference_version is not None
                    else None,
                    "disabled": source == "request" and value is None,
                }
            )
        )
    return result


async def freeze_practice_run(
    session: AsyncSession, run: PracticeRun, settings: Any, output_schema: dict[str, Any]
) -> ManagedPromptSnapshot:
    definition = await session.scalar(
        select(PromptDefinition)
        .where(PromptDefinition.definition_key == ROOT_KEY)
        .with_for_update()
    )
    if (
        definition is None
        or definition.runtime_status != "enabled"
        or definition.active_version_id is None
    ):
        raise unavailable()
    service = PromptService(None, run.owner_user_id, settings)  # type: ignore[arg-type]
    version = await service._version(session, definition.active_version_id)
    if version.status != "published":
        raise unavailable()
    composition = await service._composition(session, version)
    # 被停用的共享片段阻止新任务，已入队任务仍由不可变快照复现。
    for part in composition:
        obj = await service._version(session, part.version_id)
        owner = await service._definition(session, obj.definition_id, True)
        if owner.runtime_status != "enabled":
            raise unavailable()
    model = model_configuration(settings)
    await session.flush()
    snapshot = ManagedPromptSnapshot(
        agent_run_id=uuid4(),
        root_prompt_version_id=version.id,
        composition=[PromptPartSnapshot.model_validate(part.model_dump()) for part in composition],
        contract_sha256=CONTRACT_SHA256,
        output_schema_sha256=canonical_hash(output_schema),
        model=model["model"],
        model_parameters=model["parameters"],
        context_sources=context_sources(run.input_snapshot),
    )
    session.add(
        AgentRun(
            id=snapshot.agent_run_id,
            owner_user_id=run.owner_user_id,
            practice_run_id=run.id,
            agent_key=snapshot.agent_key,
            scene_key=snapshot.scene_key,
            root_prompt_version_id=version.id,
            snapshot=snapshot.model_dump(mode="json"),
            input_reference={"practice_run_id": str(run.id), "input_digest": run.input_digest},
            output_reference=None,
            status="pending",
            request_id=None,
            trace_ids=[],
        )
    )
    run.input_snapshot = {**run.input_snapshot, "managed_prompt": snapshot.model_dump(mode="json")}
    return snapshot


async def load_practice_prompt(
    session: AsyncSession, snapshot: ManagedPromptSnapshot, settings: Any
) -> RenderedManagedPrompt:
    agent = await session.get(AgentRun, snapshot.agent_run_id)
    if (
        agent is None
        or agent.snapshot != snapshot.model_dump(mode="json")
        or snapshot.contract_sha256 != CONTRACT_SHA256
    ):
        raise unavailable()
    service = PromptService(None, agent.owner_user_id, settings)  # type: ignore[arg-type]
    root = await service._version(session, snapshot.root_prompt_version_id)
    if root.status not in {"published", "retired"}:
        raise unavailable()
    # 只投影定义身份，不读取运行开关或active指针；后续停用/发布不影响此任务。
    rows = (
        await session.scalars(
            select(PromptVersionDependency)
            .where(PromptVersionDependency.root_version_id == root.id)
            .order_by(PromptVersionDependency.slot, PromptVersionDependency.position)
        )
    ).all()
    actual = []
    for row in rows:
        key = await session.scalar(
            select(PromptDefinition.definition_key)
            .join(PromptVersion, PromptVersion.definition_id == PromptDefinition.id)
            .where(PromptVersion.id == row.dependency_version_id)
        )
        actual.append(
            {
                "version_id": str(row.dependency_version_id),
                "definition_key": key,
                "slot": row.slot,
                "position": row.position,
                "sha256": row.dependency_sha256,
            }
        )
    key = await session.scalar(
        select(PromptDefinition.definition_key).where(PromptDefinition.id == root.definition_id)
    )
    actual.append(
        {
            "version_id": str(root.id),
            "definition_key": key,
            "slot": "task",
            "position": 0,
            "sha256": root.content_sha256,
        }
    )
    if key != ROOT_KEY or actual != [part.model_dump(mode="json") for part in snapshot.composition]:
        raise unavailable()
    messages = []
    for part in snapshot.composition:
        version = await service._version(session, part.version_id)
        if (
            version.status not in {"published", "retired"}
            or content_hash(version.content) != part.sha256
        ):
            raise unavailable()
        messages.append(
            render(
                version.content,
                [Variable.model_validate(value) for value in version.variables],
                {"agent_key": snapshot.agent_key, "scene_key": snapshot.scene_key},
            )
        )
    messages.append(
        "由代码固定的输出契约："
        + snapshot.output_schema_sha256
        + "；仅输出符合output_schema的JSON。工具列表为空。"
    )
    return RenderedManagedPrompt(system_messages=messages, snapshot=snapshot)
