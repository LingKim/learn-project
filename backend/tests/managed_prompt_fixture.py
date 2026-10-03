"""旧练习回归也走真实草稿→评测→发布，不为测试绕过生产入队门禁。"""

from uuid import uuid4

from test_prompt_integration import seed_published

from xuemian_ai.accounts.models import User
from xuemian_ai.prompt_management.schemas import StatusRequest
from xuemian_ai.prompt_management.service import PromptService


async def publish_test_prompt(sessions, settings):
    async with sessions.begin() as session:
        admin = User(
            username="managed" + uuid4().hex[:16],
            nickname="Synthetic prompt admin",
            password_hash="not-login",
            role="admin",
            status="active",
        )
        session.add(admin)
        await session.flush()
    domain = PromptService(sessions, admin.id, settings)
    for definition in await domain.bootstrap():
        if definition.runtime_status != "enabled":
            await domain.status(
                definition.id,
                StatusRequest(
                    expected_active_version_id=definition.active_version_id,
                    runtime_status="enabled",
                ),
            )
    await seed_published(domain)
