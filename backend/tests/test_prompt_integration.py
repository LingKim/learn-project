"""仅显式隔离 PostgreSQL 上验证发布门禁和运行快照，模型提供者完全合成。"""

import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from test_prompt_contract import SyntheticProvider

from xuemian_ai.accounts.models import User
from xuemian_ai.core.config import get_settings
from xuemian_ai.core.errors import ConflictError, ForbiddenError, UpstreamServiceError
from xuemian_ai.infrastructure.database import create_database_engine, create_session_factory
from xuemian_ai.practice.generation import generation_schema
from xuemian_ai.practice.models import PracticeRun, PracticeSet
from xuemian_ai.prompt_management.models import PromptVersion
from xuemian_ai.prompt_management.registry import GLOBAL_KEY, ROOT_KEY, VARIABLES
from xuemian_ai.prompt_management.runtime import freeze_practice_run, load_practice_prompt
from xuemian_ai.prompt_management.schemas import (
    DependencyInput,
    DraftCreate,
    DraftPatch,
    PublishRequest,
    RollbackRequest,
    StatusRequest,
)
from xuemian_ai.prompt_management.service import PromptService

pytestmark = pytest.mark.skipif(
    not os.getenv("PROMPT_INTEGRATION_DB"), reason="explicit isolated database required"
)


@pytest_asyncio.fixture
async def domain():
    settings = get_settings()
    assert settings.environment == "test"
    engine = create_database_engine(settings.database_url.get_secret_value())
    sessions = create_session_factory(engine)
    async with engine.connect() as connection:
        assert (
            await connection.scalar(text("SELECT current_database()"))
            == os.environ["PROMPT_INTEGRATION_DB"]
        )
    async with sessions.begin() as session:
        user = User(
            username="prompt" + uuid4().hex[:16],
            nickname="Synthetic admin",
            password_hash="not-login",
            status="active",
            role="admin",
        )
        session.add(user)
        await session.flush()
    service = PromptService(sessions, user.id, settings)
    yield service
    await engine.dispose()


async def seed_published(domain):
    definitions = await domain.bootstrap()
    global_def = next(item for item in definitions if item.definition_key == GLOBAL_KEY)
    root_def = next(item for item in definitions if item.definition_key == ROOT_KEY)
    # 隔离库可由其他测试已发布，始终克隆为新草稿执行真实验证器。
    global_draft = await domain.create_draft(
        global_def.id,
        DraftCreate(
            expected_active_version_id=global_def.active_version_id,
            source_version_id=global_def.active_version_id,
            change_description="合成公共片段测试",
        ),
    )
    result = await domain.evaluate(global_draft.id, SyntheticProvider())
    assert result.passed and len(result.case_results) == 4
    global_version = await domain.publish(
        global_draft.id,
        PublishRequest(
            expected_active_version_id=global_def.active_version_id,
            expected_revision=global_draft.revision,
        ),
    )
    root_draft = await domain.create_draft(
        root_def.id,
        DraftCreate(
            expected_active_version_id=root_def.active_version_id,
            content="受管练习任务 {{scene_key}}。严格按输出契约生成。",
            change_description="合成任务片段测试",
            dependencies=[DependencyInput(version_id=global_version.id, slot="global")],
        ),
    )
    assert (await domain.evaluate(root_draft.id, SyntheticProvider())).passed
    root_version = await domain.publish(
        root_draft.id,
        PublishRequest(
            expected_active_version_id=root_def.active_version_id,
            expected_revision=root_draft.revision,
        ),
    )
    return root_def, root_version


async def test_bootstrap_draft_only_no_auto_publication_and_no_privileged_uuid(domain):
    definitions = await domain.bootstrap()
    assert {item.definition_key for item in definitions} == {GLOBAL_KEY, ROOT_KEY}
    async with domain.sessions.begin() as session:
        user = User(
            username="denied" + uuid4().hex[:16],
            nickname="Synthetic learner",
            password_hash="not-login",
            status="active",
            role="user",
        )
        session.add(user)
        await session.flush()
    with pytest.raises(ForbiddenError):
        await PromptService(domain.sessions, user.id, domain.settings).bootstrap()


async def test_eval_content_change_stales_publish_and_rollback_creates_new_version(domain):
    definition, published = await seed_published(domain)
    candidate = await domain.create_draft(
        definition.id,
        DraftCreate(
            expected_active_version_id=published.id,
            source_version_id=published.id,
            change_description="候选草稿",
        ),
    )
    assert (await domain.evaluate(candidate.id, SyntheticProvider())).passed
    changed = await domain.patch(
        candidate.id,
        DraftPatch(
            expected_revision=candidate.revision,
            content=candidate.content + "新规则",
            variables=VARIABLES,
            dependencies=[
                DependencyInput(version_id=item.version_id, slot=item.slot, position=item.position)
                for item in candidate.dependencies
            ],
            change_description="评测后变更",
        ),
    )
    with pytest.raises(ConflictError) as error:
        await domain.publish(
            changed.id,
            PublishRequest(
                expected_active_version_id=published.id, expected_revision=changed.revision
            ),
        )
    assert error.value.error_key == "PROMPT_EVALUATION_STALE"
    rollback = await domain.rollback(
        definition.id,
        RollbackRequest(
            expected_active_version_id=published.id,
            target_version_id=published.id,
            reason="合成回滚原因",
        ),
    )
    assert rollback.id != published.id and rollback.status == "published"
    assert rollback.rollback_from_version_id == published.id
    assert (await domain.version(published.id)).status == "retired"
    with pytest.raises(ConflictError):
        await domain.publish(
            changed.id,
            PublishRequest(
                expected_active_version_id=published.id, expected_revision=changed.revision
            ),
        )


async def test_runtime_freezes_and_survives_disable_model_change_and_retirement(domain):
    definition, published = await seed_published(domain)
    config = {
        "topic": "合成事务",
        "source_mode": "general",
        "difficulty": "medium",
        "question_count": 1,
        "question_types": {"single_choice": 1},
    }
    schema = generation_schema(config)
    async with domain.sessions.begin() as session:
        obj = PracticeSet(
            owner_user_id=domain.actor,
            title="合成",
            config=config,
            request_key=uuid4(),
            input_digest="a" * 64,
        )
        session.add(obj)
        await session.flush()
        run = PracticeRun(
            owner_user_id=domain.actor,
            set_id=obj.id,
            operation="generate",
            request_key=uuid4(),
            input_digest="b" * 64,
            input_snapshot={
                "config": config,
                "effective_context": {
                    "values": {"target_job": None},
                    "sources": {"target_job": "explicit"},
                },
            },
            manifest={},
        )
        session.add(run)
        await session.flush()
        snapshot = await freeze_practice_run(session, run, domain.settings, schema)
        assert run.input_snapshot["managed_prompt"]["root_prompt_version_id"] == str(published.id)
        assert snapshot.context_sources[0].disabled
    await domain.status(
        definition.id,
        StatusRequest(expected_active_version_id=published.id, runtime_status="disabled"),
    )
    async with domain.sessions.begin() as session:
        rendered = await load_practice_prompt(
            session,
            snapshot,
            domain.settings.model_copy(update={"learning_answer_model": "changed-model"}),
        )
        assert rendered.snapshot.model == snapshot.model and len(rendered.system_messages) == 3
        second = PracticeRun(
            owner_user_id=domain.actor,
            set_id=obj.id,
            operation="generate",
            request_key=uuid4(),
            input_digest="c" * 64,
            input_snapshot={"config": config},
            manifest={},
        )
        session.add(second)
        await session.flush()
        with pytest.raises(UpstreamServiceError) as error:
            await freeze_practice_run(session, second, domain.settings, schema)
        assert error.value.error_key == "PROMPT_RUNTIME_UNAVAILABLE"
    await domain.status(
        definition.id,
        StatusRequest(expected_active_version_id=published.id, runtime_status="enabled"),
    )
    await domain.rollback(
        definition.id,
        RollbackRequest(
            expected_active_version_id=published.id,
            target_version_id=published.id,
            reason="运行后回滚",
        ),
    )
    async with domain.sessions() as session:
        assert (await load_practice_prompt(session, snapshot, domain.settings)).snapshot == snapshot
        version = await session.get(PromptVersion, published.id)
        assert version.status == "retired"


async def test_http_admin_before_lookup_and_private_audit(domain):
    from types import SimpleNamespace

    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from xuemian_ai.api.prompts import router
    from xuemian_ai.auth.dependencies import current_user_model
    from xuemian_ai.core.problem_details import register_problem_handlers
    from xuemian_ai.prompt_management.models import PromptAuditEvent

    app = FastAPI()
    app.state.infrastructure = SimpleNamespace(sessions=domain.sessions)
    register_problem_handlers(app)
    app.include_router(router, prefix="/api/v1")
    async with domain.sessions() as session:
        admin = await session.get(User, domain.actor)
    app.dependency_overrides[current_user_model] = lambda: admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/admin/prompt-definitions")
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert all("content" not in value for value in response.json()["data"])
        app.dependency_overrides[current_user_model] = lambda: SimpleNamespace(
            id=domain.actor, role="user"
        )
        response = await client.get(f"/api/v1/admin/prompt-versions/{uuid4()}")
        assert (
            response.status_code == 403 and response.json()["error_key"] == "PROMPT_ADMIN_REQUIRED"
        )
        assert response.headers["cache-control"] == "no-store"
        app.dependency_overrides[current_user_model] = lambda: admin
        response = await client.patch(
            f"/api/v1/admin/prompt-versions/{uuid4()}",
            json={"content": "SENSITIVE_SYNTHETIC_SENTINEL"},
        )
        assert response.status_code == 422 and "SENSITIVE_SYNTHETIC_SENTINEL" not in response.text
        assert response.headers["cache-control"] == "no-store"
    async with domain.sessions() as session:
        audits = (
            await session.scalars(
                select(PromptAuditEvent).where(PromptAuditEvent.actor_user_id == domain.actor)
            )
        ).all()
        assert any(
            value.action == "request_denied" and value.outcome == "denied" for value in audits
        )
        assert all(not hasattr(value, "payload") for value in audits)
