"""管理事务负责版本门禁；在线模型调用在事务外，仅回写可核验的合成评测证据。"""

import asyncio
import difflib
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from xuemian_ai.agent_runs.contracts import canonical_hash
from xuemian_ai.core.errors import ConflictError, NotFoundError
from xuemian_ai.core.responses import PageResponse, page_response
from xuemian_ai.practice.generation import GeneratedQuestions, generation_schema
from xuemian_ai.practice.schemas import PracticeConfig
from xuemian_ai.prompt_management.evaluation import (
    CASES,
    SUITE_SHA256,
    SUITE_VERSION,
    EvaluationProvider,
    QwenEvaluationProvider,
    assert_case,
    evaluation_fingerprint,
)
from xuemian_ai.prompt_management.models import (
    PromptAuditEvent,
    PromptDefinition,
    PromptEvaluationRun,
    PromptEvaluationSuite,
    PromptVersion,
    PromptVersionDependency,
)
from xuemian_ai.prompt_management.registry import (
    BOOTSTRAP_CONTENT,
    CONTRACT_SHA256,
    ENTRIES,
    GLOBAL_KEY,
    MODEL_PARAMETERS,
    ROOT_KEY,
    VARIABLES,
    PracticeInputContext,
    entry,
    model_configuration,
)
from xuemian_ai.prompt_management.rendering import (
    bounded_data,
    invalid,
    render,
    resolve_fields,
    validate_template,
)
from xuemian_ai.prompt_management.schemas import (
    AuditView,
    DefinitionView,
    DependencyInput,
    DependencyView,
    DiffView,
    DraftCreate,
    DraftPatch,
    EvaluationView,
    PreviewRequest,
    PreviewView,
    PublishRequest,
    RollbackRequest,
    StatusRequest,
    Variable,
    VersionSummary,
    VersionView,
)


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def conflict(key: str = "PROMPT_VERSION_CONFLICT") -> ConflictError:
    return ConflictError("提示词版本或评测条件已改变，请重新读取", error_key=key)


class PromptService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        actor: UUID,
        settings: Any,
        request_id: str = "",
    ) -> None:
        self.sessions, self.actor, self.settings = sessions, actor, settings
        self.request_id = request_id[:128]

    def _audit(
        self,
        session: AsyncSession,
        action: str,
        target: UUID | None = None,
        number: int | None = None,
        outcome: str = "succeeded",
    ) -> None:
        session.add(
            PromptAuditEvent(
                actor_user_id=self.actor,
                action=action,
                outcome=outcome,
                target_id=target,
                version=number,
                request_id=self.request_id,
            )
        )

    async def denied(self, action: str, target: UUID | None = None) -> None:
        async with self.sessions.begin() as session:
            self._audit(session, action, target, outcome="denied")

    async def _definition(
        self, session: AsyncSession, id: UUID, lock: bool = False
    ) -> PromptDefinition:
        query = select(PromptDefinition).where(PromptDefinition.id == id)
        obj = await session.scalar(
            query.with_for_update().execution_options(populate_existing=True) if lock else query
        )
        if obj is None:
            raise NotFoundError(error_key="PROMPT_NOT_FOUND")
        return obj

    async def _version(self, session: AsyncSession, id: UUID, lock: bool = False) -> PromptVersion:
        obj = await session.get(PromptVersion, id)
        if obj is None:
            raise NotFoundError(error_key="PROMPT_NOT_FOUND")
        if lock:
            await self._definition(session, obj.definition_id, True)
            obj = await session.scalar(
                select(PromptVersion)
                .where(PromptVersion.id == id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            assert obj
        return obj

    async def _dependencies(
        self, session: AsyncSession, obj: PromptVersion
    ) -> list[DependencyView]:
        rows = (
            await session.scalars(
                select(PromptVersionDependency)
                .where(PromptVersionDependency.root_version_id == obj.id)
                .order_by(PromptVersionDependency.slot, PromptVersionDependency.position)
            )
        ).all()
        result = []
        for row in rows:
            child = await self._version(session, row.dependency_version_id)
            definition = await self._definition(session, child.definition_id)
            if (
                child.status not in {"published", "retired"}
                or child.content_sha256 != content_hash(child.content)
                or child.content_sha256 != row.dependency_sha256
            ):
                raise conflict("PROMPT_DEPENDENCY_INVALID")
            result.append(
                DependencyView(
                    version_id=child.id,
                    definition_key=definition.definition_key,
                    slot=cast(Literal["global", "agent"], row.slot),
                    position=row.position,
                    sha256=row.dependency_sha256,
                )
            )
        return result

    async def _set_dependencies(
        self,
        session: AsyncSession,
        obj: PromptVersion,
        definition: PromptDefinition,
        inputs: list[DependencyInput],
    ) -> None:
        registered = entry(definition.definition_key)
        allowed = {(value["definition_key"], value["slot"]) for value in registered.dependencies}
        seen: set[tuple[str, int]] = set()
        children = []
        for value in inputs:
            child = await self._version(session, value.version_id)
            child_def = await self._definition(session, child.definition_id)
            if (
                (child_def.definition_key, value.slot) not in allowed
                or value.position != 0
                or (value.slot, value.position) in seen
                or child.status not in {"published", "retired"}
                or child_def.template_kind == "task"
                or child.content_sha256 != content_hash(child.content)
            ):
                raise conflict("PROMPT_DEPENDENCY_INVALID")
            seen.add((value.slot, value.position))
            children.append(
                PromptVersionDependency(
                    root_version_id=obj.id,
                    dependency_version_id=child.id,
                    slot=value.slot,
                    position=value.position,
                    dependency_sha256=child.content_sha256,
                )
            )
        await session.execute(
            delete(PromptVersionDependency).where(PromptVersionDependency.root_version_id == obj.id)
        )
        session.add_all(children)

    async def _summary(self, session: AsyncSession, obj: PromptVersion) -> VersionSummary:
        evaluation = await session.scalar(
            select(PromptEvaluationRun)
            .where(PromptEvaluationRun.prompt_version_id == obj.id)
            .order_by(PromptEvaluationRun.created_at.desc())
            .limit(1)
        )
        view = VersionSummary.model_validate(obj)
        view.latest_evaluation = EvaluationView.model_validate(evaluation) if evaluation else None
        return view

    async def _view(self, session: AsyncSession, obj: PromptVersion) -> VersionView:
        return VersionView(
            **(await self._summary(session, obj)).model_dump(),
            content=obj.content,
            variables=[Variable.model_validate(v) for v in obj.variables],
            dependencies=await self._dependencies(session, obj),
        )

    async def _admin(self, session: AsyncSession) -> None:
        from xuemian_ai.accounts.models import User
        from xuemian_ai.core.errors import ForbiddenError

        actor = await session.get(User, self.actor)
        if (
            actor is None
            or actor.role != "admin"
            or actor.status != "active"
            or actor.deleted_at is not None
        ):
            raise ForbiddenError(error_key="PROMPT_ADMIN_REQUIRED")

    async def bootstrap(self) -> list[DefinitionView]:
        """显式CLI/测试初始化；旧指令仅成为草稿，绝不生成通过结果或活动版本。"""
        async with self.sessions.begin() as session:
            await self._admin(session)
            await session.execute(select(func.pg_advisory_xact_lock(768249001)))
            for key, registered in ENTRIES.items():
                existing = await session.scalar(
                    select(PromptDefinition).where(PromptDefinition.definition_key == key)
                )
                if existing:
                    continue
                definition = PromptDefinition(
                    id=uuid4(),
                    **registered.model_dump(
                        include={
                            "definition_key",
                            "agent_key",
                            "scene_key",
                            "template_kind",
                            "display_name",
                            "description",
                        }
                    ),
                )
                session.add(definition)
                await session.flush()
                version = PromptVersion(
                    id=uuid4(),
                    definition_id=definition.id,
                    version=1,
                    content=BOOTSTRAP_CONTENT[key],
                    content_sha256=content_hash(BOOTSTRAP_CONTENT[key]),
                    variables=[v.model_dump() for v in VARIABLES],
                    change_description="从现有指令初始化待评测草稿",
                    created_by=self.actor,
                )
                session.add(version)
                self._audit(session, "bootstrap_draft", definition.id, 1)
            await self._suite(session)
        return (await self.list_definitions(1, 100)).data

    async def _suite(self, session: AsyncSession) -> PromptEvaluationSuite:
        await session.execute(select(func.pg_advisory_xact_lock(768249002)))
        suite = await session.scalar(
            select(PromptEvaluationSuite).where(
                PromptEvaluationSuite.agent_key == "question_generator",
                PromptEvaluationSuite.scene_key == "practice_generate",
                PromptEvaluationSuite.version == SUITE_VERSION,
            )
        )
        if suite is None:
            suite = PromptEvaluationSuite(
                id=uuid4(),
                agent_key="question_generator",
                scene_key="practice_generate",
                version=SUITE_VERSION,
                status="published",
                cases=CASES,
                sha256=SUITE_SHA256,
                model_policy={"all_hard_gates": True},
                created_by=self.actor,
            )
            session.add(suite)
            await session.flush()
        if (
            suite.status != "published"
            or suite.sha256 != SUITE_SHA256
            or canonical_hash(suite.cases) != canonical_hash(CASES)
        ):
            raise conflict("PROMPT_SUITE_STALE")
        return suite

    async def list_definitions(
        self, page: int, page_size: int, **filters: str | None
    ) -> PageResponse[DefinitionView]:
        async with self.sessions() as session:
            query = select(PromptDefinition)
            for key in ("agent_key", "scene_key", "template_kind", "runtime_status"):
                if filters.get(key):
                    query = query.where(getattr(PromptDefinition, key) == filters[key])
            total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
            values = (
                await session.scalars(
                    query.order_by(PromptDefinition.definition_key)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
            return page_response(
                [self._definition_view(v) for v in values],
                page=page,
                page_size=page_size,
                total=total,
            )

    @staticmethod
    def _definition_view(obj: PromptDefinition) -> DefinitionView:
        view = DefinitionView.model_validate(obj)
        view.contract_sha256 = CONTRACT_SHA256 if obj.definition_key in ENTRIES else None
        if obj.definition_key in ENTRIES:
            view.registered_contract = {
                **entry(obj.definition_key).model_dump(mode="json"),
                "input_schema": PracticeInputContext.model_json_schema(),
                "output_schema": GeneratedQuestions.model_json_schema(),
                "model_policy": {"provider": "dashscope", "parameters": MODEL_PARAMETERS},
                "dynamic_output_schema": "由practice_generate已确认配置在入队时固定",
            }
        return view

    async def definition(self, id: UUID) -> DefinitionView:
        async with self.sessions() as session:
            return self._definition_view(await self._definition(session, id))

    async def versions(self, id: UUID, page: int, page_size: int) -> PageResponse[VersionSummary]:
        async with self.sessions() as session:
            await self._definition(session, id)
            query = select(PromptVersion).where(PromptVersion.definition_id == id)
            total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
            values = (
                await session.scalars(
                    query.order_by(PromptVersion.version.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
            return page_response(
                [await self._summary(session, v) for v in values],
                page=page,
                page_size=page_size,
                total=total,
            )

    async def version(self, id: UUID) -> VersionView:
        async with self.sessions.begin() as session:
            obj = await self._version(session, id)
            self._audit(session, "view_body", obj.id, obj.version)
            return await self._view(session, obj)

    async def _new_draft(
        self,
        session: AsyncSession,
        definition: PromptDefinition,
        body: DraftCreate,
        rollback: UUID | None = None,
    ) -> PromptVersion:
        registered = entry(definition.definition_key)
        if body.expected_active_version_id != definition.active_version_id:
            raise conflict()
        source = (
            await self._version(session, body.source_version_id) if body.source_version_id else None
        )
        if source and source.definition_id != definition.id:
            raise conflict()
        content = (
            body.content
            if body.content is not None
            else source.content
            if source
            else BOOTSTRAP_CONTENT[registered.definition_key]
        )
        variables = [Variable.model_validate(v) for v in source.variables] if source else VARIABLES
        validate_template(content, variables)
        number = (
            await session.scalar(
                select(func.max(PromptVersion.version)).where(
                    PromptVersion.definition_id == definition.id
                )
            )
            or 0
        ) + 1
        obj = PromptVersion(
            id=uuid4(),
            definition_id=definition.id,
            version=number,
            content=content,
            content_sha256=content_hash(content),
            variables=[v.model_dump() for v in variables],
            change_description=body.change_description,
            base_active_version_id=definition.active_version_id,
            rollback_from_version_id=rollback,
            created_by=self.actor,
        )
        session.add(obj)
        await session.flush()
        dependencies = (
            body.dependencies
            if body.dependencies is not None
            else [
                DependencyInput(**d.model_dump(include={"version_id", "slot", "position"}))
                for d in await self._dependencies(session, source)
            ]
            if source
            else []
        )
        await self._set_dependencies(session, obj, definition, dependencies)
        return obj

    async def create_draft(self, id: UUID, body: DraftCreate) -> VersionView:
        async with self.sessions.begin() as session:
            definition = await self._definition(session, id, True)
            obj = await self._new_draft(session, definition, body)
            self._audit(session, "create_draft", obj.id, obj.version)
            return await self._view(session, obj)

    async def patch(self, id: UUID, body: DraftPatch) -> VersionView:
        async with self.sessions.begin() as session:
            obj = await self._version(session, id, True)
            definition = await self._definition(session, obj.definition_id)
            entry(definition.definition_key)
            if obj.status != "draft" or obj.revision != body.expected_revision:
                raise conflict()
            validate_template(body.content, body.variables)
            await self._set_dependencies(session, obj, definition, body.dependencies)
            obj.content, obj.content_sha256, obj.variables, obj.change_description = (
                body.content,
                content_hash(body.content),
                [v.model_dump() for v in body.variables],
                body.change_description,
            )
            obj.revision += 1
            await session.flush()
            self._audit(session, "edit_draft", obj.id, obj.version)
            return await self._view(session, obj)

    async def diff(self, id: UUID, base_id: UUID | None = None) -> DiffView:
        async with self.sessions.begin() as session:
            obj = await self._version(session, id)
            base_id = base_id or obj.base_active_version_id
            base = await self._version(session, base_id) if base_id else None
            if base and base.definition_id != obj.definition_id:
                raise conflict()
            self._audit(session, "view_diff", obj.id, obj.version)
            return DiffView(
                version_id=id,
                base_version_id=base_id,
                content_diff="".join(
                    difflib.unified_diff(
                        (base.content if base else "").splitlines(True),
                        obj.content.splitlines(True),
                        fromfile="base",
                        tofile="candidate",
                    )
                ),
                variables_changed=obj.variables != (base.variables if base else []),
                dependencies_changed=await self._dependencies(session, obj)
                != (await self._dependencies(session, base) if base else []),
            )

    async def _composition(self, session: AsyncSession, obj: PromptVersion) -> list[DependencyView]:
        if content_hash(obj.content) != obj.content_sha256:
            raise conflict("PROMPT_HASH_MISMATCH")
        validate_template(obj.content, [Variable.model_validate(v) for v in obj.variables])
        definition = await self._definition(session, obj.definition_id)
        registered = entry(definition.definition_key)
        dependencies = await self._dependencies(session, obj)
        if {(v.definition_key, v.slot) for v in dependencies} != {
            (v["definition_key"], v["slot"]) for v in registered.dependencies
        }:
            raise conflict("PROMPT_DEPENDENCY_INVALID")
        return [
            *dependencies,
            DependencyView(
                version_id=obj.id,
                definition_key=definition.definition_key,
                slot="global" if registered.template_kind == "shared" else "task",
                position=0,
                sha256=obj.content_sha256,
            ),
        ]

    async def _messages(
        self, session: AsyncSession, obj: PromptVersion, schema: dict[str, Any]
    ) -> tuple[list[str], list[DependencyView]]:
        definition = await self._definition(session, obj.definition_id)
        composition = await self._composition(session, obj)
        trusted = {"agent_key": "question_generator", "scene_key": "practice_generate"}
        messages = []
        for part in composition:
            version = await self._version(session, part.version_id)
            if version.content_sha256 != content_hash(version.content):
                raise conflict("PROMPT_HASH_MISMATCH")
            messages.append(
                render(
                    version.content,
                    [Variable.model_validate(v) for v in version.variables],
                    trusted,
                )
            )
        # 公共片段的评测使用固定任务指令作为合成测试夹具，不把未发布草稿用于业务运行。
        if definition.definition_key == GLOBAL_KEY:
            messages.append(BOOTSTRAP_CONTENT[ROOT_KEY])
        messages.append(
            "由代码固定的输出契约："
            + canonical_hash(schema)
            + "；仅输出符合output_schema的JSON。工具列表为空。"
        )
        return messages, composition

    async def preview(self, id: UUID, body: PreviewRequest) -> PreviewView:
        async with self.sessions.begin() as session:
            obj = await self._version(session, id)
            allowed = {"config", "request", "selected_asset", "weakness", "profile", "defaults"}
            if not set(body.variables) <= allowed:
                raise invalid()
            bounded_data(body.variables)
            try:
                cfg = PracticeConfig.model_validate(
                    body.variables.get("config", CASES[0]["config"])
                )
                layers = [
                    body.variables.get(key, {})
                    for key in ("request", "selected_asset", "weakness", "profile", "defaults")
                ]
                if any(not isinstance(value, dict) for value in layers):
                    raise invalid()
                values, sources = resolve_fields(*layers)
            except (ValidationError, TypeError):
                raise invalid() from None
            schema = generation_schema(cfg.model_dump(mode="json"))
            messages, composition = await self._messages(session, obj, schema)
            self._audit(session, "preview", id, obj.version)
            return PreviewView(
                system_messages=messages,
                data_message={
                    "config": cfg.model_dump(mode="json"),
                    "effective_context": {
                        "values": values,
                        "sources": [s.model_dump(mode="json") for s in sources],
                    },
                },
                composition=composition,
                contract_sha256=CONTRACT_SHA256,
                output_schema_sha256=canonical_hash(schema),
                message_lengths=[len(m) for m in messages],
            )

    async def evaluate(
        self, id: UUID, provider: EvaluationProvider | None = None
    ) -> EvaluationView:
        async with self.sessions.begin() as session:
            await self._admin(session)
            obj = await self._version(session, id, True)
            if obj.status != "draft":
                raise conflict()
            # 同一草稿一次只执行一个评测，跨进程以持久状态约束并发。
            pending = await session.scalar(
                select(PromptEvaluationRun).where(
                    PromptEvaluationRun.prompt_version_id == id,
                    PromptEvaluationRun.status == "processing",
                )
            )
            if pending:
                if pending.started_at + timedelta(
                    seconds=self.settings.practice_run_timeout_seconds
                ) > datetime.now(UTC):
                    raise conflict("PROMPT_EVALUATION_PROCESSING")
                pending.status, pending.passed, pending.error_key = (
                    "failed",
                    False,
                    "PROMPT_EVALUATION_TIMEOUT",
                )
                pending.ended_at = datetime.now(UTC)
            suite = await self._suite(session)
            assembled = [
                await self._messages(session, obj, generation_schema(case["config"]))
                for case in CASES
            ]
            composition = [part.model_dump(mode="json") for part in assembled[0][1]]
            # 根version_id不参与内容资格，允许回滚克隆在条件完全相同时复用证据。
            fingerprint = evaluation_fingerprint(
                obj.content_sha256, obj.variables, composition[:-1], suite.id, self.settings
            )
            run = PromptEvaluationRun(
                id=uuid4(),
                prompt_version_id=id,
                evaluation_suite_id=suite.id,
                evaluation_fingerprint=fingerprint,
                model_configuration=model_configuration(self.settings),
                status="processing",
                started_at=datetime.now(UTC),
                executed_by=self.actor,
            )
            session.add(run)
            self._audit(session, "evaluate", id, obj.version)
            await session.flush()
            run_id = run.id
        results: list[dict[str, Any]] = []
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        error_key: str | None = None
        interrupted = False
        try:
            async with asyncio.timeout(self.settings.practice_run_timeout_seconds):
                for case, (messages, _) in zip(CASES, assembled, strict=True):
                    schema = generation_schema(case["config"])
                    payload = {
                        "operation": "generate",
                        "config": case["config"],
                        "effective_context": case["effective_context"],
                        "evidence": [
                            {"number": i + 1, "content": item["content"]}
                            for i, item in enumerate(case["evidence"])
                        ],
                        "output_schema": schema,
                    }
                    try:
                        raw, used = await (
                            provider or QwenEvaluationProvider(self.settings)
                        ).invoke(messages, payload, schema)
                        for key in usage:
                            usage[key] += max(0, int(used.get(key, 0)))
                        assert_case(raw, case)
                        results.append({"case_id": case["id"], "passed": True, "error_key": None})
                    except Exception:
                        results.append(
                            {
                                "case_id": case["id"],
                                "passed": False,
                                "error_key": "PROMPT_EVALUATION_FAILED",
                            }
                        )
        except TimeoutError:
            error_key = "PROMPT_EVALUATION_TIMEOUT"
        except asyncio.CancelledError:
            interrupted = True
            error_key = "PROMPT_EVALUATION_INTERRUPTED"
        passed = (
            error_key is None
            and len(results) == len(CASES)
            and all(result["passed"] for result in results)
        )
        async with self.sessions.begin() as session:
            completed = await session.get(PromptEvaluationRun, run_id)
            assert completed
            completed.case_results, completed.metrics = (
                results,
                {
                    "total": len(CASES),
                    "passed": sum(bool(r["passed"]) for r in results),
                    "usage": usage,
                },
            )
            completed.passed, completed.status, completed.error_key, completed.ended_at = (
                passed,
                "succeeded" if passed else "failed",
                error_key or (None if passed else "PROMPT_EVALUATION_FAILED"),
                datetime.now(UTC),
            )
            await session.flush()
            view = EvaluationView.model_validate(completed)
        if interrupted:
            raise asyncio.CancelledError
        return view

    async def _eligible(self, session: AsyncSession, obj: PromptVersion) -> bool:
        suite = await self._suite(session)
        composition = await self._composition(session, obj)
        fingerprint = evaluation_fingerprint(
            obj.content_sha256,
            obj.variables,
            [part.model_dump(mode="json") for part in composition[:-1]],
            suite.id,
            self.settings,
        )
        # 复用只按完整内容条件查证据，不依据“曾发布”推断通过。
        return (
            await session.scalar(
                select(PromptEvaluationRun.id)
                .where(
                    PromptEvaluationRun.evaluation_fingerprint == fingerprint,
                    PromptEvaluationRun.passed.is_(True),
                    PromptEvaluationRun.status == "succeeded",
                )
                .limit(1)
            )
            is not None
        )

    async def _publish(
        self, session: AsyncSession, obj: PromptVersion, definition: PromptDefinition
    ) -> None:
        await self._admin(session)
        entry(definition.definition_key)
        if obj.status != "draft" or obj.base_active_version_id != definition.active_version_id:
            raise conflict()
        if not await self._eligible(session, obj):
            raise conflict("PROMPT_EVALUATION_STALE")
        if definition.active_version_id:
            old = await self._version(session, definition.active_version_id)
            old.status = "retired"
            await session.flush()
        obj.status, obj.published_at, obj.published_by = "published", datetime.now(UTC), self.actor
        definition.active_version_id = obj.id
        await session.flush()

    async def publish(self, id: UUID, body: PublishRequest) -> VersionView:
        async with self.sessions.begin() as session:
            obj = await self._version(session, id, True)
            definition = await self._definition(session, obj.definition_id)
            if (
                body.expected_active_version_id != definition.active_version_id
                or body.expected_revision != obj.revision
            ):
                raise conflict()
            await self._publish(session, obj, definition)
            self._audit(session, "publish", id, obj.version)
            return await self._view(session, obj)

    async def rollback(self, id: UUID, body: RollbackRequest) -> VersionView:
        async with self.sessions.begin() as session:
            definition = await self._definition(session, id, True)
            target = await self._version(session, body.target_version_id)
            if (
                not body.reason.strip()
                or target.definition_id != id
                or target.status not in {"published", "retired"}
            ):
                raise conflict()
            obj = await self._new_draft(
                session,
                definition,
                DraftCreate(
                    expected_active_version_id=body.expected_active_version_id,
                    source_version_id=target.id,
                    change_description=body.reason,
                ),
                target.id,
            )
            if await self._eligible(session, obj):
                await self._publish(session, obj, definition)
            self._audit(session, "rollback", obj.id, obj.version)
            return await self._view(session, obj)

    async def status(self, id: UUID, body: StatusRequest) -> DefinitionView:
        async with self.sessions.begin() as session:
            definition = await self._definition(session, id, True)
            if body.expected_active_version_id != definition.active_version_id:
                raise conflict()
            if body.runtime_status == "enabled":
                entry(definition.definition_key)
            definition.runtime_status = body.runtime_status
            await session.flush()
            self._audit(session, "set_status", id)
            await session.refresh(definition)
            return self._definition_view(definition)

    async def audits(self, id: UUID, page: int, page_size: int) -> PageResponse[AuditView]:
        async with self.sessions() as session:
            await self._definition(session, id)
            ids = select(PromptVersion.id).where(PromptVersion.definition_id == id)
            query = select(PromptAuditEvent).where(
                (PromptAuditEvent.target_id == id) | PromptAuditEvent.target_id.in_(ids)
            )
            total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
            values = (
                await session.scalars(
                    query.order_by(PromptAuditEvent.created_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
            return page_response(
                [AuditView.model_validate(v) for v in values],
                page=page,
                page_size=page_size,
                total=total,
            )
