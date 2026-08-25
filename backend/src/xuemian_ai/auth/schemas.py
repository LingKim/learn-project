import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

_USERNAME_PATTERN = re.compile(r"^[a-z0-9_]{3,32}$")


def validate_password_rules(password: str) -> str:
    if len(password) < 8:
        raise ValueError("密码至少需要 8 位")
    categories = sum(
        (
            any(character.isalpha() for character in password),
            any(character.isdigit() for character in password),
            any(not character.isalnum() for character in password),
        )
    )
    if categories < 2:
        raise ValueError("密码必须包含字母、数字、符号中的至少两类")
    return password


def normalize_username(username: str) -> str:
    normalized = username.strip().lower()
    if _USERNAME_PATTERN.fullmatch(normalized) is None:
        raise ValueError("用户名只能包含小写字母、数字和下划线，长度为 3 至 32 位")
    return normalized


class RegisterRequest(BaseModel):
    username: str
    nickname: str
    password: str

    @field_validator("username")
    @classmethod
    def normalize_and_validate_username(cls, value: str) -> str:
        return normalize_username(value)

    @field_validator("nickname")
    @classmethod
    def normalize_and_validate_nickname(cls, value: str) -> str:
        normalized = value.strip()
        if not 1 <= len(normalized) <= 40:
            raise ValueError("昵称长度必须为 1 至 40 位")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_password_rules(value)


class LoginRequest(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def normalize_and_validate_username(cls, value: str) -> str:
        return normalize_username(value)

    @field_validator("password")
    @classmethod
    def validate_password_length(cls, value: str) -> str:
        if not value or len(value) > 1024:
            raise ValueError("密码不能为空且长度不能超过 1024 位")
        return value


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    nickname: str
    role: str
    status: str


class AuthPayload(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: UserView
