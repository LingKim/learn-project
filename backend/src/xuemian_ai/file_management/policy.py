from copy import deepcopy
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from xuemian_ai.core.errors import ConflictError, NotFoundError, ValidationAppError
from xuemian_ai.file_management.models import FilePolicyVersion

MIB = 1024 * 1024
GIB = 1024 * MIB

DEFAULT_RULES: dict[str, object] = {
    "avatar": {
        "extensions": ["jpg", "jpeg", "png", "webp"],
        "max_bytes": 5 * MIB,
        "max_dimension": 8192,
        "max_pixels": 40_000_000,
    },
    "knowledge_document": {
        "extensions": ["pdf", "docx", "txt", "md"],
        "max_bytes": 50 * MIB,
        "pdf_max_pages": 500,
        "text_max_characters": 2_000_000,
        "docx_max_uncompressed_bytes": 200 * MIB,
        "docx_max_compression_ratio": 100,
        "docx_max_paragraphs": 100_000,
    },
    "resume": {
        "extensions": ["pdf", "docx"],
        "max_bytes": 10 * MIB,
        "pdf_max_pages": 50,
        "text_max_characters": 500_000,
        "docx_max_uncompressed_bytes": 50 * MIB,
        "docx_max_compression_ratio": 100,
        "docx_max_paragraphs": 20_000,
    },
    "job_description": {
        "extensions": ["pdf", "docx", "txt", "md"],
        "max_bytes": 10 * MIB,
        "pdf_max_pages": 50,
        "text_max_characters": 500_000,
        "docx_max_uncompressed_bytes": 50 * MIB,
        "docx_max_compression_ratio": 100,
        "docx_max_paragraphs": 20_000,
    },
    "real_interview_recording": {
        "extensions": ["mp3", "m4a", "wav", "webm", "ogg"],
        "max_bytes": 500 * MIB,
        "max_duration_seconds": 10_800,
    },
    "mock_interview_recording": {
        "extensions": ["webm", "m4a"],
        "max_bytes": 500 * MIB,
        "max_duration_seconds": 3_600,
    },
    "limits": {
        "concurrent_sessions": 3,
        "sessions_per_hour": 30,
        "pending_bytes": 2 * GIB,
        "long_lived_bytes": 10 * GIB,
        "recording_bytes": 10 * GIB,
    },
}

HARD_LIMITS: dict[str, object] = {
    "avatar": {
        "max_bytes": 10 * MIB,
        "max_dimension": 12000,
        "max_pixels": 60_000_000,
    },
    "knowledge_document": {
        "max_bytes": 100 * MIB,
        "pdf_max_pages": 1000,
        "text_max_characters": 5_000_000,
        "docx_max_uncompressed_bytes": 400 * MIB,
        "docx_max_compression_ratio": 100,
        "docx_max_paragraphs": 200_000,
    },
    "resume": {
        "max_bytes": 20 * MIB,
        "pdf_max_pages": 100,
        "text_max_characters": 1_000_000,
        "docx_max_uncompressed_bytes": 100 * MIB,
        "docx_max_compression_ratio": 100,
        "docx_max_paragraphs": 40_000,
    },
    "job_description": {
        "max_bytes": 20 * MIB,
        "pdf_max_pages": 100,
        "text_max_characters": 1_000_000,
        "docx_max_uncompressed_bytes": 100 * MIB,
        "docx_max_compression_ratio": 100,
        "docx_max_paragraphs": 40_000,
    },
    "real_interview_recording": {
        "max_bytes": GIB,
        "max_duration_seconds": 21_600,
    },
    "mock_interview_recording": {
        "max_bytes": GIB,
        "max_duration_seconds": 5_400,
    },
    "limits": {
        "concurrent_sessions": 20,
        "sessions_per_hour": 300,
        "pending_bytes": 10 * GIB,
        "long_lived_bytes": 50 * GIB,
        "recording_bytes": 50 * GIB,
    },
}


def validate_policy_rules(rules: dict[str, object]) -> dict[str, object]:
    normalized = deepcopy(rules)
    if set(normalized) != set(DEFAULT_RULES):
        raise ValidationAppError("文件策略用途不完整", error_key="FILE_POLICY_INVALID")
    for purpose, default_value in DEFAULT_RULES.items():
        value = normalized.get(purpose)
        if not isinstance(value, dict) or not isinstance(default_value, dict):
            raise ValidationAppError("文件策略结构不合法", error_key="FILE_POLICY_INVALID")
        required = set(default_value)
        if set(value) != required:
            raise ValidationAppError("文件策略字段不完整", error_key="FILE_POLICY_INVALID")
        hard = cast(dict[str, object], HARD_LIMITS[purpose])
        for key, item in value.items():
            if key == "extensions":
                if not isinstance(item, list) or not item:
                    raise ValidationAppError(
                        "文件类型白名单不能为空", error_key="FILE_POLICY_INVALID"
                    )
                continue
            hard_value = hard[key]
            if (
                not isinstance(item, int)
                or not isinstance(hard_value, int)
                or item <= 0
                or item > hard_value
            ):
                raise ValidationAppError("文件策略超过系统硬上限", error_key="FILE_POLICY_LIMIT")
    return normalized


def knowledge_rules(policy: FilePolicyVersion) -> dict[str, object]:
    return cast(dict[str, object], policy.rules["knowledge_document"])


class FilePolicyService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_default(self) -> FilePolicyVersion:
        await self._session.execute(select(func.pg_advisory_xact_lock(867530903)))
        existing = await self.effective(required=False)
        if existing is not None:
            return existing
        latest = await self._session.scalar(select(func.max(FilePolicyVersion.version)))
        policy = FilePolicyVersion(
            version=int(latest or 0) + 1,
            status="published",
            rules=deepcopy(DEFAULT_RULES),
            published_at=datetime.now(UTC),
        )
        self._session.add(policy)
        await self._session.flush()
        return policy

    async def effective(self, *, required: bool = True) -> FilePolicyVersion | None:
        policy = cast(
            FilePolicyVersion | None,
            await self._session.scalar(
                select(FilePolicyVersion).where(FilePolicyVersion.status == "published")
            ),
        )
        if policy is None and required:
            raise NotFoundError("尚未发布文件策略", error_key="FILE_POLICY_NOT_FOUND")
        return policy

    async def list_versions(self) -> list[FilePolicyVersion]:
        return list(
            (
                await self._session.scalars(
                    select(FilePolicyVersion).order_by(FilePolicyVersion.version.desc())
                )
            ).all()
        )

    async def create_draft(
        self, rules: dict[str, object], base_version_id: UUID | None
    ) -> FilePolicyVersion:
        latest = int(await self._session.scalar(select(func.max(FilePolicyVersion.version))) or 0)
        policy = FilePolicyVersion(
            version=latest + 1,
            status="draft",
            rules=validate_policy_rules(rules),
            base_version_id=base_version_id,
        )
        self._session.add(policy)
        await self._session.flush()
        return policy

    async def update_draft(self, policy_id: UUID, rules: dict[str, object]) -> FilePolicyVersion:
        policy = await self._session.get(FilePolicyVersion, policy_id)
        if policy is None:
            raise NotFoundError(error_key="FILE_POLICY_NOT_FOUND")
        if policy.status != "draft":
            raise ConflictError("已发布策略不可修改", error_key="FILE_POLICY_IMMUTABLE")
        policy.rules = validate_policy_rules(rules)
        await self._session.flush()
        await self._session.refresh(policy)
        return policy

    async def publish(
        self, policy_id: UUID, base_version_id: UUID | None, actor_id: UUID
    ) -> FilePolicyVersion:
        policy = await self._session.get(FilePolicyVersion, policy_id)
        if policy is None:
            raise NotFoundError(error_key="FILE_POLICY_NOT_FOUND")
        if policy.status != "draft":
            raise ConflictError("策略状态不允许发布", error_key="FILE_POLICY_IMMUTABLE")
        current = await self.effective(required=False)
        current_id = current.id if current is not None else None
        if current_id != base_version_id or policy.base_version_id != base_version_id:
            raise ConflictError("文件策略基准版本已变化", error_key="FILE_POLICY_VERSION_CONFLICT")
        if current is not None:
            current.status = "retired"
        policy.status = "published"
        policy.published_by = actor_id
        policy.published_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.refresh(policy)
        return policy
