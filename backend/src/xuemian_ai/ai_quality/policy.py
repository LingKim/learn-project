"""状态转换和输入约束与 HTTP、数据库实现分离，便于验证业务边界。"""

import re
from datetime import UTC, datetime, timedelta

from xuemian_ai.core.errors import ConflictError, ValidationAppError

TRANSITIONS: dict[str, set[str]] = {
    "submitted": {"triaging", "closed"},
    "triaging": {"waiting_user", "investigating", "resolved", "closed"},
    "waiting_user": {"triaging", "investigating", "resolved", "closed"},
    "investigating": {"waiting_user", "resolved", "closed"},
    "resolved": {"closed"},
    "closed": set(),
}
TECHNICAL_CODES = {
    "parsing_gap",
    "stale_index",
    "fts_filter",
    "vector_recall",
    "fusion",
    "rerank",
    "evidence_gate",
}
SECRET = re.compile(
    r"(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|\bAKIA[A-Z0-9]{16}\b|\bsk-[A-Za-z0-9_-]{20,}|"
    r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b)",
    re.IGNORECASE,
)


def validate_text(value: str) -> None:
    if SECRET.search(value) or re.search(r"<\s*(script|iframe)\b|javascript\s*:", value, re.I):
        raise ValidationAppError("请移除脚本或凭据后再提交", error_key="QUALITY_CONTENT_INVALID")


def check_version(actual: int, expected: int) -> None:
    if actual != expected:
        raise ConflictError(error_key="QUALITY_VERSION_CONFLICT")


def transition_allowed(current: str, target: str) -> None:
    if target not in TRANSITIONS[current]:
        raise ConflictError(error_key="QUALITY_STATE_CONFLICT")


def effective_closed(status: str, resolved_at: datetime | None, confirmation_days: int) -> bool:
    return status == "closed" or (
        status == "resolved"
        and resolved_at is not None
        and resolved_at + timedelta(days=confirmation_days) <= datetime.now(UTC)
    )
