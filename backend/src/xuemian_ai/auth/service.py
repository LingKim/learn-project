import hmac
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from xuemian_ai.accounts.models import AuthAuditEvent, AuthSession, User
from xuemian_ai.auth.rate_limit import AuthRateLimiter
from xuemian_ai.auth.schemas import LoginRequest, RegisterRequest, UserView
from xuemian_ai.auth.security import PasswordService, TokenBundle, TokenService
from xuemian_ai.core.errors import ConflictError, UnauthorizedError
from xuemian_ai.knowledge_bases.models import KnowledgeBase


@dataclass(frozen=True, slots=True)
class RequestMetadata:
    request_id: str | None
    ip_address: str | None
    user_agent: str | None


@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    tokens: TokenBundle
    user: UserView


class AuthenticationService:
    def __init__(
        self,
        session: AsyncSession,
        password_service: PasswordService,
        token_service: TokenService,
        rate_limiter: AuthRateLimiter,
    ) -> None:
        self._session = session
        self._passwords = password_service
        self._tokens = token_service
        self._rate_limiter = rate_limiter

    async def register(
        self, request: RegisterRequest, metadata: RequestMetadata
    ) -> AuthenticationResult:
        ip_key = self._tokens.fingerprint(metadata.ip_address) or "unknown"
        await self._rate_limiter.record_registration_attempt(ip_key)

        now = datetime.now(UTC)
        user_id = uuid4()
        session_id = uuid4()
        family_id = uuid4()
        tokens = self._tokens.issue_tokens(
            user_id=user_id,
            session_id=session_id,
            family_id=family_id,
            role="user",
        )
        user = User(
            id=user_id,
            username=request.username,
            nickname=request.nickname,
            password_hash=self._passwords.hash(request.password),
            role="user",
            status="active",
            last_login_at=now,
            created_by=user_id,
            updated_by=user_id,
        )
        try:
            async with self._session.begin():
                self._session.add(user)
                await self._session.flush()
                self._session.add(
                    KnowledgeBase(
                        owner_user_id=user_id,
                        name="默认知识库",
                        is_default=True,
                        created_by=user_id,
                        updated_by=user_id,
                    )
                )
                self._session.add(
                    self._new_session(
                        session_id=session_id,
                        family_id=family_id,
                        user_id=user_id,
                        tokens=tokens,
                        metadata=metadata,
                    )
                )
                self._session.add(
                    self._audit(
                        event_type="register",
                        outcome="success",
                        metadata=metadata,
                        user_id=user_id,
                        username=request.username,
                    )
                )
        except IntegrityError as exc:
            if self._constraint_name(exc) == "users_username_key":
                raise ConflictError("用户名已被使用", error_key="AUTH_USERNAME_TAKEN") from exc
            raise
        return AuthenticationResult(tokens=tokens, user=UserView.model_validate(user))

    async def login(self, request: LoginRequest, metadata: RequestMetadata) -> AuthenticationResult:
        username_key = self._tokens.fingerprint(request.username) or "unknown"
        ip_key = self._tokens.fingerprint(metadata.ip_address) or "unknown"
        await self._rate_limiter.ensure_login_allowed(username_key, ip_key)

        async with self._session.begin():
            user = await self._find_login_user(request.username)
            verification = (
                self._passwords.verify_and_update(request.password, user.password_hash)
                if user is not None
                else (False, None)
            )

        if user is None or not verification[0]:
            await self._record_failed_login(request.username, metadata)
            await self._rate_limiter.record_login_failure(username_key, ip_key)
            raise self._invalid_credentials()

        updated_hash = verification[1]
        now = datetime.now(UTC)
        session_id = uuid4()
        family_id = uuid4()
        tokens = self._tokens.issue_tokens(
            user_id=user.id,
            session_id=session_id,
            family_id=family_id,
            role=user.role,
        )
        async with self._session.begin():
            locked_user = await self._session.scalar(
                select(User).where(User.id == user.id).with_for_update()
            )
            if locked_user is None or locked_user.deleted_at is not None:
                raise self._invalid_credentials()
            if locked_user.status != "active":
                raise self._invalid_credentials()
            if updated_hash is not None:
                locked_user.password_hash = updated_hash
            locked_user.last_login_at = now
            locked_user.updated_by = locked_user.id
            self._session.add(
                self._new_session(
                    session_id=session_id,
                    family_id=family_id,
                    user_id=locked_user.id,
                    tokens=tokens,
                    metadata=metadata,
                )
            )
            self._session.add(
                self._audit(
                    event_type="login",
                    outcome="success",
                    metadata=metadata,
                    user_id=locked_user.id,
                    username=locked_user.username,
                )
            )
        await self._rate_limiter.clear_login_account(username_key)
        return AuthenticationResult(tokens=tokens, user=UserView.model_validate(user))

    async def refresh(self, refresh_token: str, metadata: RequestMetadata) -> AuthenticationResult:
        claims = self._tokens.decode_refresh(refresh_token)
        presented_digest = self._tokens.refresh_digest(refresh_token)
        replayed = False
        result: AuthenticationResult | None = None

        async with self._session.begin():
            auth_session = await self._session.scalar(
                select(AuthSession).where(AuthSession.id == claims.session_id).with_for_update()
            )
            user = await self._session.get(User, claims.user_id)
            now = datetime.now(UTC)
            if (
                auth_session is None
                or user is None
                or auth_session.user_id != claims.user_id
                or auth_session.family_id != claims.family_id
                or auth_session.revoked_at is not None
                or auth_session.absolute_expires_at <= now
                or user.deleted_at is not None
                or user.status != "active"
            ):
                raise UnauthorizedError(
                    "登录状态已失效，请重新登录",
                    error_key="AUTH_SESSION_REVOKED",
                )

            if auth_session.current_refresh_jti != claims.jti or not self._constant_compare(
                auth_session.current_refresh_digest, presented_digest
            ):
                auth_session.revoked_at = now
                auth_session.revoke_reason = "refresh_replay"
                self._session.add(
                    self._audit(
                        event_type="refresh_replay",
                        outcome="failure",
                        metadata=metadata,
                        user_id=user.id,
                        username=user.username,
                        reason_code="AUTH_REFRESH_TOKEN_REPLAYED",
                    )
                )
                replayed = True
            else:
                tokens = self._tokens.issue_tokens(
                    user_id=user.id,
                    session_id=auth_session.id,
                    family_id=auth_session.family_id,
                    role=user.role,
                    absolute_expires_at=auth_session.absolute_expires_at,
                )
                auth_session.current_refresh_jti = tokens.refresh_jti
                auth_session.current_refresh_digest = self._tokens.refresh_digest(
                    tokens.refresh_token
                )
                auth_session.last_used_at = now
                self._session.add(
                    self._audit(
                        event_type="refresh",
                        outcome="success",
                        metadata=metadata,
                        user_id=user.id,
                        username=user.username,
                    )
                )
                result = AuthenticationResult(
                    tokens=tokens,
                    user=UserView.model_validate(user),
                )

        if replayed:
            raise UnauthorizedError(
                "登录状态已失效，请重新登录",
                error_key="AUTH_REFRESH_TOKEN_INVALID",
            )
        if result is None:
            raise UnauthorizedError(
                "登录状态已失效，请重新登录",
                error_key="AUTH_REFRESH_TOKEN_INVALID",
            )
        return result

    async def current_user(self, access_token: str) -> UserView:
        claims = self._tokens.decode_access(access_token)
        async with self._session.begin():
            auth_session = await self._session.get(AuthSession, claims.session_id)
            user = await self._session.get(User, claims.user_id)
            now = datetime.now(UTC)
            if (
                auth_session is None
                or user is None
                or auth_session.user_id != user.id
                or auth_session.revoked_at is not None
                or auth_session.absolute_expires_at <= now
                or user.deleted_at is not None
                or user.status != "active"
            ):
                raise UnauthorizedError(
                    "登录状态已失效，请重新登录",
                    error_key="AUTH_SESSION_REVOKED",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return UserView.model_validate(user)

    async def logout(
        self,
        refresh_token: str | None,
        access_token: str | None,
        metadata: RequestMetadata,
    ) -> None:
        session_id = self._resolve_logout_session(refresh_token, access_token)
        if session_id is None:
            return
        async with self._session.begin():
            auth_session = await self._session.get(AuthSession, session_id)
            if auth_session is None or auth_session.revoked_at is not None:
                return
            now = datetime.now(UTC)
            auth_session.revoked_at = now
            auth_session.revoke_reason = "logout"
            user = await self._session.get(User, auth_session.user_id)
            self._session.add(
                self._audit(
                    event_type="logout",
                    outcome="success",
                    metadata=metadata,
                    user_id=auth_session.user_id,
                    username=user.username if user is not None else None,
                )
            )

    async def _find_login_user(self, username: str) -> User | None:
        return cast(
            User | None,
            await self._session.scalar(
                select(User).where(
                    User.username == username,
                    User.status == "active",
                    User.deleted_at.is_(None),
                )
            ),
        )

    async def _record_failed_login(self, username: str, metadata: RequestMetadata) -> None:
        async with self._session.begin():
            self._session.add(
                self._audit(
                    event_type="login",
                    outcome="failure",
                    metadata=metadata,
                    username=username,
                    reason_code="AUTH_INVALID_CREDENTIALS",
                )
            )

    def _new_session(
        self,
        *,
        session_id: UUID,
        family_id: UUID,
        user_id: UUID,
        tokens: TokenBundle,
        metadata: RequestMetadata,
    ) -> AuthSession:
        return AuthSession(
            id=session_id,
            user_id=user_id,
            family_id=family_id,
            current_refresh_jti=tokens.refresh_jti,
            current_refresh_digest=self._tokens.refresh_digest(tokens.refresh_token),
            absolute_expires_at=tokens.absolute_expires_at,
            ip_hash=self._tokens.fingerprint(metadata.ip_address),
            user_agent_summary=self._safe_user_agent(metadata.user_agent),
        )

    def _audit(
        self,
        *,
        event_type: str,
        outcome: str,
        metadata: RequestMetadata,
        user_id: UUID | None = None,
        username: str | None = None,
        reason_code: str | None = None,
    ) -> AuthAuditEvent:
        return AuthAuditEvent(
            user_id=user_id,
            username_fingerprint=self._tokens.fingerprint(username),
            event_type=event_type,
            outcome=outcome,
            reason_code=reason_code,
            request_id=metadata.request_id,
            ip_hash=self._tokens.fingerprint(metadata.ip_address),
            user_agent_summary=self._safe_user_agent(metadata.user_agent),
            occurred_at=datetime.now(UTC),
        )

    def _resolve_logout_session(
        self, refresh_token: str | None, access_token: str | None
    ) -> UUID | None:
        if refresh_token:
            try:
                return self._tokens.decode_refresh(refresh_token).session_id
            except UnauthorizedError:
                pass
        if access_token:
            try:
                return self._tokens.decode_access(access_token).session_id
            except UnauthorizedError:
                pass
        return None

    @staticmethod
    def _safe_user_agent(user_agent: str | None) -> str | None:
        return user_agent[:256] if user_agent else None

    @staticmethod
    def _constant_compare(left: str, right: str) -> bool:
        return hmac.compare_digest(left, right)

    @staticmethod
    def _constraint_name(exc: IntegrityError) -> str | None:
        driver_cause = getattr(exc.orig, "__cause__", None)
        value = getattr(driver_cause, "constraint_name", None)
        return value if isinstance(value, str) else None

    @staticmethod
    def _invalid_credentials() -> UnauthorizedError:
        return UnauthorizedError(
            "用户名或密码错误",
            error_key="AUTH_INVALID_CREDENTIALS",
            headers={"WWW-Authenticate": "Bearer"},
        )
