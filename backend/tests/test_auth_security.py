from uuid import uuid4

import pytest
from pydantic import ValidationError

from xuemian_ai.auth.schemas import RegisterRequest
from xuemian_ai.auth.security import PasswordService, TokenService
from xuemian_ai.core.config import Settings
from xuemian_ai.core.errors import UnauthorizedError

_ACCESS_SECRET = "a" * 64
_REFRESH_SECRET = "b" * 64
_DIGEST_SECRET = "c" * 64
_FINGERPRINT_SECRET = "d" * 64


def auth_settings() -> Settings:
    return Settings(
        auth_access_secret=_ACCESS_SECRET,
        auth_refresh_secret=_REFRESH_SECRET,
        auth_refresh_digest_secret=_DIGEST_SECRET,
        auth_fingerprint_secret=_FINGERPRINT_SECRET,
    )


def test_register_request_normalizes_username_and_nickname() -> None:
    request = RegisterRequest(username="  Alice_01  ", nickname="  小林  ", password="abc12345")

    assert request.username == "alice_01"
    assert request.nickname == "小林"


@pytest.mark.parametrize("username", ["ab", "含中文", "has-dash", "space name"])
def test_register_request_rejects_invalid_username(username: str) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(username=username, nickname="用户", password="abc12345")


@pytest.mark.parametrize("password", ["short1", "abcdefgh", "12345678", "!!!!!!!!"])
def test_register_request_rejects_weak_password(password: str) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(username="alice", nickname="用户", password=password)


def test_password_service_hashes_and_verifies_argon2id() -> None:
    service = PasswordService()
    password_hash = service.hash("abc12345")

    verified, updated_hash = service.verify_and_update("abc12345", password_hash)

    assert password_hash.startswith("$argon2")
    assert verified is True
    assert updated_hash is None
    assert service.verify_and_update("wrong-password", password_hash)[0] is False


def test_token_service_issues_distinct_typed_tokens() -> None:
    service = TokenService(auth_settings())
    user_id = uuid4()
    session_id = uuid4()
    family_id = uuid4()

    bundle = service.issue_tokens(
        user_id=user_id,
        session_id=session_id,
        family_id=family_id,
        role="user",
    )

    access = service.decode_access(bundle.access_token)
    refresh = service.decode_refresh(bundle.refresh_token)
    assert access.user_id == user_id
    assert access.session_id == session_id
    assert refresh.session_id == session_id
    assert refresh.family_id == family_id
    assert bundle.access_expires_in == 900
    assert service.refresh_digest(bundle.refresh_token) != bundle.refresh_token


def test_token_type_cannot_be_swapped() -> None:
    service = TokenService(auth_settings())
    bundle = service.issue_tokens(
        user_id=uuid4(),
        session_id=uuid4(),
        family_id=uuid4(),
        role="user",
    )

    with pytest.raises(UnauthorizedError) as access_error:
        service.decode_access(bundle.refresh_token)
    with pytest.raises(UnauthorizedError) as refresh_error:
        service.decode_refresh(bundle.access_token)

    assert access_error.value.error_key == "AUTH_ACCESS_TOKEN_INVALID"
    assert refresh_error.value.error_key == "AUTH_REFRESH_TOKEN_INVALID"


def test_settings_rejects_shared_authentication_secret() -> None:
    with pytest.raises(ValidationError, match="must be distinct"):
        Settings(
            auth_access_secret=_ACCESS_SECRET,
            auth_refresh_secret=_ACCESS_SECRET,
            auth_refresh_digest_secret=_DIGEST_SECRET,
            auth_fingerprint_secret=_FINGERPRINT_SECRET,
        )
