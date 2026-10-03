"""验证已有真实日调度入口确实清除超过宽限期的加密诊断正文。"""

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from xuemian_ai.ai_quality.models import AIQualityCase, DiagnosticAccessGrant, DiagnosticSnapshot
from xuemian_ai.ai_quality.schemas import GrantRevoke
from xuemian_ai.file_management.worker import FileScheduler

pytest_plugins = ["test_ai_quality_integration"]
pytestmark = pytest.mark.skipif(
    not os.getenv("AI_QUALITY_INTEGRATION_DB"), reason="explicit isolated database required"
)


async def test_daily_scheduler_physically_clears_revoked_snapshot(quality):
    q = quality
    case = await q.user.create(q.request)
    grant = case.grants[0]
    await q.user.grant_revoke(
        case.id,
        grant.id,
        GrantRevoke(expected_version=case.version, expected_grant_version=grant.version),
    )
    async with q.sessions.begin() as session:
        revoked = await session.get(DiagnosticAccessGrant, grant.id)
        revoked.revoked_at = datetime.now(UTC) - timedelta(days=8)
        assert await session.scalar(
            select(DiagnosticSnapshot.id).where(DiagnosticSnapshot.grant_id == grant.id)
        )
    scheduler = FileScheduler(q.settings)
    try:
        await scheduler.run_daily()
    finally:
        await scheduler.close()
    async with q.sessions() as session:
        assert (
            await session.scalar(
                select(DiagnosticSnapshot.id).where(DiagnosticSnapshot.grant_id == grant.id)
            )
            is None
        )
        persisted = await session.get(AIQualityCase, case.id)
        assert persisted.statement_ciphertext is None and persisted.statement_key_id is None
