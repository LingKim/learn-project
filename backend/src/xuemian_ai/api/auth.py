from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from xuemian_ai.auth.rate_limit import AuthRateLimiter
from xuemian_ai.auth.schemas import AuthPayload, LoginRequest, RegisterRequest, UserView
from xuemian_ai.auth.security import PasswordService, TokenService
from xuemian_ai.auth.service import AuthenticationResult, AuthenticationService, RequestMetadata
from xuemian_ai.core.config import Settings, get_settings
from xuemian_ai.core.errors import ForbiddenError, UnauthorizedError
from xuemian_ai.core.responses import ApiResponse, success_response
from xuemian_ai.core.status_codes import ApiStatusCode

router = APIRouter(prefix="/auth", tags=["authentication"])
_bearer = HTTPBearer(auto_error=False)
_password_service = PasswordService()
_REFRESH_COOKIE = "xuemian_refresh_token"


async def database_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.infrastructure.sessions() as session:
        yield session


def authentication_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(database_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthenticationService:
    infrastructure = request.app.state.infrastructure
    return AuthenticationService(
        session=session,
        password_service=_password_service,
        token_service=TokenService(settings),
        rate_limiter=AuthRateLimiter(infrastructure.redis, settings.auth_redis_key_prefix),
    )


def request_metadata(request: Request) -> RequestMetadata:
    return RequestMetadata(
        request_id=getattr(request.state, "request_id", None),
        ip_address=request.client.host if request.client is not None else None,
        user_agent=request.headers.get("user-agent"),
    )


def validate_origin(request: Request, settings: Settings) -> None:
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.allowed_origins:
        raise ForbiddenError("请求来源不受信任", error_key="AUTH_ORIGIN_NOT_ALLOWED")


def set_refresh_cookie(
    response: Response, result: AuthenticationResult, settings: Settings
) -> None:
    max_age = max(
        0,
        int((result.tokens.absolute_expires_at - datetime.now(UTC)).total_seconds()),
    )
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=result.tokens.refresh_token,
        max_age=max_age,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=_REFRESH_COOKIE,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def auth_payload(result: AuthenticationResult) -> AuthPayload:
    return AuthPayload(
        access_token=result.tokens.access_token,
        expires_in=result.tokens.access_expires_in,
        user=result.user,
    )


@router.post(
    "/register",
    operation_id="auth_register",
    response_model=ApiResponse[AuthPayload],
    status_code=ApiStatusCode.CREATED,
)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    service: Annotated[AuthenticationService, Depends(authentication_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApiResponse[AuthPayload]:
    result = await service.register(body, request_metadata(request))
    set_refresh_cookie(response, result, settings)
    return success_response(auth_payload(result), message="注册成功", code=ApiStatusCode.CREATED)


@router.post(
    "/login",
    operation_id="auth_login",
    response_model=ApiResponse[AuthPayload],
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    service: Annotated[AuthenticationService, Depends(authentication_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApiResponse[AuthPayload]:
    result = await service.login(body, request_metadata(request))
    set_refresh_cookie(response, result, settings)
    return success_response(auth_payload(result), message="登录成功")


@router.post(
    "/refresh",
    operation_id="auth_refresh",
    response_model=ApiResponse[AuthPayload],
)
async def refresh(
    request: Request,
    response: Response,
    service: Annotated[AuthenticationService, Depends(authentication_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    refresh_token: Annotated[str | None, Cookie(alias=_REFRESH_COOKIE)] = None,
) -> ApiResponse[AuthPayload]:
    validate_origin(request, settings)
    if refresh_token is None:
        raise UnauthorizedError(
            "登录状态已失效，请重新登录",
            error_key="AUTH_REFRESH_TOKEN_INVALID",
        )
    result = await service.refresh(refresh_token, request_metadata(request))
    set_refresh_cookie(response, result, settings)
    return success_response(auth_payload(result), message="会话已刷新")


@router.get("/me", operation_id="auth_me", response_model=ApiResponse[UserView])
async def me(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    service: Annotated[AuthenticationService, Depends(authentication_service)],
) -> ApiResponse[UserView]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError(
            "请先登录",
            error_key="AUTH_ACCESS_TOKEN_INVALID",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await service.current_user(credentials.credentials)
    return success_response(user)


@router.post("/logout", operation_id="auth_logout", response_model=ApiResponse[None])
async def logout(
    request: Request,
    response: Response,
    service: Annotated[AuthenticationService, Depends(authentication_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    refresh_token: Annotated[str | None, Cookie(alias=_REFRESH_COOKIE)] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> ApiResponse[None]:
    validate_origin(request, settings)
    access_token = None
    if authorization and authorization.lower().startswith("bearer "):
        access_token = authorization[7:].strip()
    await service.logout(refresh_token, access_token, request_metadata(request))
    clear_refresh_cookie(response, settings)
    return success_response(None, message="已退出登录")
