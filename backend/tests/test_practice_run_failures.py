from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from xuemian_ai.practice.models import PracticeRun
from xuemian_ai.practice.service import PracticeService


@pytest.mark.parametrize(
    "status,error_key,retryable,expected_status,expected_retryable",
    [
        ("processing", "PRACTICE_PROVIDER_UNAVAILABLE", False, "failed", False),
        ("processing", "PRACTICE_PROVIDER_UNAVAILABLE", True, "failed", True),
        ("processing", "PRACTICE_SOURCE_CHANGED", True, "failed", False),
        ("processing", "LEARNING_TARGET_MISMATCH", True, "failed", False),
        ("cancel_requested", "PRACTICE_PROVIDER_UNAVAILABLE", True, "cancelled", False),
    ],
)
async def test_failure_respects_retry_decision_and_business_fences(
    status, error_key, retryable, expected_status, expected_retryable
):
    run = PracticeRun(id=uuid4(), lease_token=uuid4(), status=status)
    session = AsyncMock()
    session.scalar.return_value = run
    sessions = MagicMock()
    sessions.begin.return_value.__aenter__ = AsyncMock(return_value=session)
    sessions.begin.return_value.__aexit__ = AsyncMock(return_value=False)

    service = PracticeService(sessions, uuid4())
    assert await service.fail_run(run.id, run.lease_token, error_key, retryable)
    assert run.status == run.stage == expected_status
    assert run.error_key == error_key
    assert run.retryable is expected_retryable
    assert run.lease_token is None
    assert run.ended_at is not None
