from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

TrimmedNickname = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)
]
TargetLevel = Literal["intern", "junior", "intermediate", "senior", "expert"]
PreferredLanguage = Literal["zh-CN", "en-US"]


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_tags(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = item.strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key not in seen:
            result.append(normalized)
            seen.add(key)
    return result


class ActiveWeaknessView(BaseModel):
    id: UUID
    name: str
    domain: str | None = None
    severity: str
    mastery_status: str
    source_summary: str
    last_verified_at: str | None = None


class UserProfileView(BaseModel):
    username: str
    nickname: str
    target_job: str | None
    experience_months: int | None
    experience_display: str | None
    target_level: TargetLevel | None
    target_skills: list[str] | None
    focus_topics: list[str] | None
    learning_goal: str | None
    preferred_language: PreferredLanguage | None
    avatar_set: bool
    avatar_url: str | None
    version: int
    active_weaknesses: list[ActiveWeaknessView]


class UserProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=0)
    nickname: TrimmedNickname | None = None
    target_job: str | None = Field(default=None, max_length=120)
    experience_months: int | None = Field(default=None, ge=0, le=720)
    target_level: TargetLevel | None = None
    target_skills: list[str] | None = Field(default=None, max_length=30)
    focus_topics: list[str] | None = Field(default=None, max_length=30)
    learning_goal: str | None = Field(default=None, max_length=1000)
    preferred_language: PreferredLanguage | None = None

    @field_validator("nickname")
    @classmethod
    def nickname_must_not_be_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("昵称不能为空")
        return value

    @field_validator("target_job", "learning_goal")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("target_skills")
    @classmethod
    def normalize_skills(cls, value: list[str] | None) -> list[str] | None:
        normalized = _normalize_tags(value)
        if normalized is not None and any(len(item) > 50 for item in normalized):
            raise ValueError("目标技能单项最多 50 个字符")
        return normalized

    @field_validator("focus_topics")
    @classmethod
    def normalize_topics(cls, value: list[str] | None) -> list[str] | None:
        normalized = _normalize_tags(value)
        if normalized is not None and any(len(item) > 80 for item in normalized):
            raise ValueError("关注知识点单项最多 80 个字符")
        return normalized


class AvatarUploadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    size: int = Field(gt=0, le=5 * 1024 * 1024)
    declared_mime: Literal["image/jpeg", "image/png", "image/webp"]
    profile_version: int = Field(ge=0)


class AvatarUploadPlan(BaseModel):
    id: UUID
    upload_url: str
    expires_at: str
    status: str


class AvatarUploadCompleteView(BaseModel):
    id: UUID
    status: str
    failure_code: str | None
    profile_version: int | None = None


class AvatarDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=0)
