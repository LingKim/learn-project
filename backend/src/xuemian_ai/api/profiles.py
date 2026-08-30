from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from xuemian_ai.accounts.models import User
from xuemian_ai.auth.dependencies import current_user_model, database_session
from xuemian_ai.core.config import Settings, get_settings
from xuemian_ai.core.responses import ApiResponse, success_response
from xuemian_ai.profiles.schemas import (
    AvatarDeleteRequest,
    AvatarUploadCompleteView,
    AvatarUploadCreate,
    AvatarUploadPlan,
    UserProfilePatch,
    UserProfileView,
)
from xuemian_ai.profiles.service import UserProfileService

router = APIRouter(prefix="/users/me", tags=["user-profile"])


def profile_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(database_session)],
    user: Annotated[User, Depends(current_user_model)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserProfileService:
    return UserProfileService(
        session=session,
        storage=request.app.state.infrastructure.object_storage,
        settings=settings,
        user=user,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get(
    "/profile",
    operation_id="user_profile_get",
    response_model=ApiResponse[UserProfileView],
)
async def get_user_profile(
    service: Annotated[UserProfileService, Depends(profile_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ApiResponse[UserProfileView]:
    async with session.begin():
        result = await service.get_profile()
    return success_response(result)


@router.patch(
    "/profile",
    operation_id="user_profile_update",
    response_model=ApiResponse[UserProfileView],
)
async def update_user_profile(
    body: UserProfilePatch,
    service: Annotated[UserProfileService, Depends(profile_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ApiResponse[UserProfileView]:
    async with session.begin():
        result = await service.update_profile(body)
    return success_response(result, message="个人资料已更新")


@router.post(
    "/avatar-upload-sessions",
    operation_id="avatar_upload_sessions_create",
    response_model=ApiResponse[AvatarUploadPlan],
)
async def create_avatar_upload_session(
    body: AvatarUploadCreate,
    service: Annotated[UserProfileService, Depends(profile_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> ApiResponse[AvatarUploadPlan]:
    async with session.begin():
        result = await service.create_avatar_upload(body, idempotency_key)
    return success_response(result, message="头像上传会话已创建")


@router.post(
    "/avatar-upload-sessions/{upload_id}/complete",
    operation_id="avatar_upload_sessions_complete",
    response_model=ApiResponse[AvatarUploadCompleteView],
)
async def complete_avatar_upload_session(
    upload_id: UUID,
    service: Annotated[UserProfileService, Depends(profile_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ApiResponse[AvatarUploadCompleteView]:
    async with session.begin():
        result = await service.complete_avatar_upload(upload_id)
    return success_response(result, message="头像已提交处理")


@router.get("/avatar", operation_id="user_avatar_get", response_class=Response)
async def get_user_avatar(
    service: Annotated[UserProfileService, Depends(profile_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> Response:
    async with session.begin():
        content = await service.avatar_content()
    return Response(
        content=content,
        media_type="image/webp",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.delete(
    "/avatar",
    operation_id="user_avatar_delete",
    response_model=ApiResponse[UserProfileView],
)
async def delete_user_avatar(
    body: AvatarDeleteRequest,
    service: Annotated[UserProfileService, Depends(profile_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ApiResponse[UserProfileView]:
    async with session.begin():
        result = await service.delete_avatar(body.version)
    return success_response(result, message="头像已删除")
