from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from xuemian_ai.accounts.models import AuthSession, User
from xuemian_ai.auth.security import TokenService
from xuemian_ai.core.config import Settings, get_settings
from xuemian_ai.core.errors import UnauthorizedError

bearer = HTTPBearer(auto_error=False)


async def database_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.infrastructure.sessions() as session:
        yield session


async def current_user_model(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[AsyncSession, Depends(database_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError(
            "请先登录",
            error_key="AUTH_ACCESS_TOKEN_INVALID",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = TokenService(settings).decode_access(credentials.credentials)
    auth_session = await session.get(AuthSession, claims.session_id)
    user = cast(User | None, await session.get(User, claims.user_id))
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
    # 认证查询与后续业务事务使用同一个 request-scoped session。
    # 显式结束只读事务，避免业务路由的 session.begin() 嵌套失败。
    await session.commit()
    return user
