import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash

from xuemian_ai.core.config import Settings
from xuemian_ai.core.errors import UnauthorizedError

_JWT_ALGORITHM = "HS256"


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: UUID
    session_id: UUID
    role: str


@dataclass(frozen=True, slots=True)
class RefreshClaims:
    user_id: UUID
    session_id: UUID
    family_id: UUID
    jti: UUID


@dataclass(frozen=True, slots=True)
class TokenBundle:
    access_token: str
    refresh_token: str
    refresh_jti: UUID
    absolute_expires_at: datetime
    access_expires_in: int


class PasswordService:
    def __init__(self) -> None:
        self._hasher = PasswordHash.recommended()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify_and_update(self, password: str, password_hash: str) -> tuple[bool, str | None]:
        return self._hasher.verify_and_update(password, password_hash)


class TokenService:
    def __init__(self, settings: Settings) -> None:
        self._access_secret = settings.auth_access_secret.get_secret_value()
        self._refresh_secret = settings.auth_refresh_secret.get_secret_value()
        self._digest_secret = settings.auth_refresh_digest_secret.get_secret_value().encode()
        self._fingerprint_secret = settings.auth_fingerprint_secret.get_secret_value().encode()
        self._issuer = settings.auth_issuer
        self._audience = settings.auth_audience
        self._access_lifetime = timedelta(minutes=settings.auth_access_minutes)
        self._refresh_lifetime = timedelta(days=settings.auth_refresh_days)

    @property
    def access_expires_in(self) -> int:
        return int(self._access_lifetime.total_seconds())

    def issue_tokens(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        family_id: UUID,
        role: str,
        absolute_expires_at: datetime | None = None,
    ) -> TokenBundle:
        now = datetime.now(UTC)
        refresh_expires_at = absolute_expires_at or now + self._refresh_lifetime
        refresh_jti = uuid4()
        access_token = jwt.encode(
            {
                "sub": str(user_id),
                "sid": str(session_id),
                "role": role,
                "type": "access",
                "iss": self._issuer,
                "aud": self._audience,
                "iat": now,
                "exp": now + self._access_lifetime,
                "jti": str(uuid4()),
            },
            self._access_secret,
            algorithm=_JWT_ALGORITHM,
        )
        refresh_token = jwt.encode(
            {
                "sub": str(user_id),
                "sid": str(session_id),
                "family_id": str(family_id),
                "type": "refresh",
                "iss": self._issuer,
                "aud": self._audience,
                "iat": now,
                "exp": refresh_expires_at,
                "jti": str(refresh_jti),
            },
            self._refresh_secret,
            algorithm=_JWT_ALGORITHM,
        )
        return TokenBundle(
            access_token=access_token,
            refresh_token=refresh_token,
            refresh_jti=refresh_jti,
            absolute_expires_at=refresh_expires_at,
            access_expires_in=self.access_expires_in,
        )

    def decode_access(self, token: str) -> AccessClaims:
        payload = self._decode(token, self._access_secret, "access", "AUTH_ACCESS_TOKEN_INVALID")
        try:
            return AccessClaims(
                user_id=UUID(payload["sub"]),
                session_id=UUID(payload["sid"]),
                role=str(payload["role"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise UnauthorizedError(
                "登录状态无效，请重新登录",
                error_key="AUTH_ACCESS_TOKEN_INVALID",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    def decode_refresh(self, token: str) -> RefreshClaims:
        payload = self._decode(token, self._refresh_secret, "refresh", "AUTH_REFRESH_TOKEN_INVALID")
        try:
            return RefreshClaims(
                user_id=UUID(payload["sub"]),
                session_id=UUID(payload["sid"]),
                family_id=UUID(payload["family_id"]),
                jti=UUID(payload["jti"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise UnauthorizedError(
                "登录状态已失效，请重新登录",
                error_key="AUTH_REFRESH_TOKEN_INVALID",
            ) from exc

    def refresh_digest(self, token: str) -> str:
        return hmac.new(self._digest_secret, token.encode(), sha256).hexdigest()

    def fingerprint(self, value: str | None) -> str | None:
        if not value:
            return None
        return hmac.new(self._fingerprint_secret, value.encode(), sha256).hexdigest()

    def _decode(
        self,
        token: str,
        secret: str,
        expected_type: str,
        error_key: str,
    ) -> dict[str, Any]:
        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=[_JWT_ALGORITHM],
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["sub", "sid", "type", "iss", "aud", "iat", "exp", "jti"]},
            )
            if payload.get("type") != expected_type:
                raise InvalidTokenError("unexpected token type")
            return payload
        except InvalidTokenError as exc:
            headers = {"WWW-Authenticate": "Bearer"} if expected_type == "access" else None
            raise UnauthorizedError(
                "登录状态无效，请重新登录",
                error_key=error_key,
                headers=headers,
            ) from exc
