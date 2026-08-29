from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from xuemian_ai.accounts.models import User
from xuemian_ai.auth.dependencies import current_user_model, database_session
from xuemian_ai.core.config import Settings, get_settings
from xuemian_ai.core.errors import ForbiddenError
from xuemian_ai.core.responses import ApiResponse, PageResponse, page_response, success_response
from xuemian_ai.file_management.policy import FilePolicyService
from xuemian_ai.file_management.schemas import (
    CompleteUploadRequest,
    DeleteRequest,
    DeleteResult,
    DeletionImpactView,
    DownloadUrlView,
    DuplicateResolutionRequest,
    FilePolicyDraftRequest,
    FilePolicyPublishRequest,
    FilePolicyUpdateRequest,
    FilePolicyView,
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    KnowledgeBaseView,
    KnowledgeFileMove,
    KnowledgeFileUpdate,
    KnowledgeFileView,
    SignedPart,
    SignPartsRequest,
    UploadPlan,
    UploadSessionCreate,
    UploadSessionView,
)
from xuemian_ai.file_management.service import FileManagementService

router = APIRouter(tags=["file-management"])


def file_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(database_session)],
    user: Annotated[User, Depends(current_user_model)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileManagementService:
    return FileManagementService(
        session=session,
        redis=request.app.state.infrastructure.redis,
        storage=request.app.state.infrastructure.object_storage,
        settings=settings,
        user=user,
        request_id=getattr(request.state, "request_id", None),
        ip_address=request.client.host if request.client is not None else None,
    )


def require_admin(user: User) -> None:
    if user.role != "admin":
        raise ForbiddenError("仅管理员可以管理文件策略", error_key="ADMIN_REQUIRED")


@router.get(
    "/knowledge-bases",
    operation_id="knowledge_bases_list",
    response_model=PageResponse[KnowledgeBaseView],
)
async def list_knowledge_bases(
    service: Annotated[FileManagementService, Depends(file_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PageResponse[KnowledgeBaseView]:
    items, total = await service.list_knowledge_bases(page, page_size)
    return page_response(
        [KnowledgeBaseView.model_validate(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post(
    "/knowledge-bases",
    operation_id="knowledge_bases_create",
    response_model=ApiResponse[KnowledgeBaseView],
)
async def create_knowledge_base(
    body: KnowledgeBaseCreate,
    service: Annotated[FileManagementService, Depends(file_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ApiResponse[KnowledgeBaseView]:
    async with session.begin():
        item = await service.create_knowledge_base(body.name)
    return success_response(KnowledgeBaseView.model_validate(item), message="知识库已创建")


@router.patch(
    "/knowledge-bases/{knowledge_base_id}",
    operation_id="knowledge_bases_update",
    response_model=ApiResponse[KnowledgeBaseView],
)
async def update_knowledge_base(
    knowledge_base_id: UUID,
    body: KnowledgeBaseUpdate,
    service: Annotated[FileManagementService, Depends(file_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ApiResponse[KnowledgeBaseView]:
    async with session.begin():
        item = await service.rename_knowledge_base(knowledge_base_id, body.name)
    return success_response(KnowledgeBaseView.model_validate(item), message="知识库已重命名")


@router.get(
    "/knowledge-bases/{knowledge_base_id}/deletion-impact",
    operation_id="knowledge_bases_deletion_impact",
    response_model=ApiResponse[DeletionImpactView],
)
async def knowledge_base_deletion_impact(
    knowledge_base_id: UUID,
    service: Annotated[FileManagementService, Depends(file_service)],
    mode: str = Query(default="SOURCE_ONLY", pattern="^(SOURCE_ONLY|CASCADE)$"),
) -> ApiResponse[DeletionImpactView]:
    return success_response(
        await service.deletion_impact("knowledge_base", knowledge_base_id, mode)
    )


@router.delete(
    "/knowledge-bases/{knowledge_base_id}",
    operation_id="knowledge_bases_delete",
    response_model=ApiResponse[DeleteResult],
)
async def delete_knowledge_base(
    knowledge_base_id: UUID,
    body: DeleteRequest,
    service: Annotated[FileManagementService, Depends(file_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ApiResponse[DeleteResult]:
    async with session.begin():
        result = await service.delete_knowledge_base(
            knowledge_base_id, body.confirmation_token, body.mode
        )
    return success_response(result, message="知识库已删除")


@router.post(
    "/knowledge-bases/{knowledge_base_id}/file-upload-sessions",
    operation_id="file_upload_sessions_create",
    response_model=ApiResponse[UploadPlan],
)
async def create_upload_session(
    knowledge_base_id: UUID,
    body: UploadSessionCreate,
    service: Annotated[FileManagementService, Depends(file_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> ApiResponse[UploadPlan]:
    async with session.begin():
        plan = await service.create_upload_session(knowledge_base_id, body, idempotency_key)
    return success_response(plan, message="上传会话已创建")


@router.post(
    "/file-upload-sessions/{session_id}/sign-parts",
    operation_id="file_upload_sessions_sign_parts",
    response_model=ApiResponse[list[SignedPart]],
)
async def sign_upload_parts(
    session_id: UUID,
    body: SignPartsRequest,
    service: Annotated[FileManagementService, Depends(file_service)],
) -> ApiResponse[list[SignedPart]]:
    return success_response(await service.sign_parts(session_id, body.part_numbers))


@router.post(
    "/file-upload-sessions/{session_id}/renew-upload-url",
    operation_id="file_upload_sessions_renew",
    response_model=ApiResponse[UploadPlan],
)
async def renew_upload_url(
    session_id: UUID,
    service: Annotated[FileManagementService, Depends(file_service)],
) -> ApiResponse[UploadPlan]:
    return success_response(await service.renew_upload_url(session_id))


@router.post(
    "/file-upload-sessions/{session_id}/complete",
    operation_id="file_upload_sessions_complete",
    response_model=ApiResponse[UploadSessionView],
)
async def complete_upload(
    session_id: UUID,
    body: CompleteUploadRequest,
    service: Annotated[FileManagementService, Depends(file_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ApiResponse[UploadSessionView]:
    parts: list[dict[str, int | str]] = [
        {"PartNumber": part.part_number, "ETag": part.etag} for part in body.parts
    ]
    async with session.begin():
        result = await service.complete_upload(session_id, parts)
    return success_response(result, message="文件已提交校验")


@router.get(
    "/file-upload-sessions/{session_id}",
    operation_id="file_upload_sessions_get",
    response_model=ApiResponse[UploadSessionView],
)
async def get_upload_session(
    session_id: UUID,
    service: Annotated[FileManagementService, Depends(file_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ApiResponse[UploadSessionView]:
    async with session.begin():
        result = await service.get_upload_session(session_id)
    return success_response(result)


@router.delete(
    "/file-upload-sessions/{session_id}",
    operation_id="file_upload_sessions_cancel",
    response_model=ApiResponse[UploadSessionView],
)
async def cancel_upload_session(
    session_id: UUID,
    service: Annotated[FileManagementService, Depends(file_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ApiResponse[UploadSessionView]:
    async with session.begin():
        result = await service.cancel_upload(session_id)
    return success_response(result, message="上传会话已取消")


@router.post(
    "/file-upload-sessions/{session_id}/duplicate-resolution",
    operation_id="file_upload_sessions_resolve_duplicate",
    response_model=ApiResponse[UploadSessionView],
)
async def resolve_duplicate(
    session_id: UUID,
    body: DuplicateResolutionRequest,
    service: Annotated[FileManagementService, Depends(file_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ApiResponse[UploadSessionView]:
    async with session.begin():
        result = await service.resolve_duplicate(session_id, body.action)
    return success_response(result, message="重复文件处理完成")


@router.get(
    "/knowledge-bases/{knowledge_base_id}/files",
    operation_id="knowledge_base_files_list",
    response_model=PageResponse[KnowledgeFileView],
)
async def list_knowledge_files(
    knowledge_base_id: UUID,
    service: Annotated[FileManagementService, Depends(file_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(max_length=255)] = None,
    status: Annotated[str | None, Query(max_length=32)] = None,
) -> PageResponse[KnowledgeFileView]:
    items, total = await service.list_files(knowledge_base_id, page, page_size, search, status)
    return page_response(items, page=page, page_size=page_size, total=total)


@router.patch(
    "/knowledge-bases/{knowledge_base_id}/files/{knowledge_file_id}",
    operation_id="knowledge_base_files_update",
    response_model=ApiResponse[KnowledgeFileView],
)
async def rename_knowledge_file(
    knowledge_base_id: UUID,
    knowledge_file_id: UUID,
    body: KnowledgeFileUpdate,
    service: Annotated[FileManagementService, Depends(file_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ApiResponse[KnowledgeFileView]:
    async with session.begin():
        result = await service.rename_file(knowledge_base_id, knowledge_file_id, body.display_name)
    return success_response(result, message="文件已重命名")


@router.post(
    "/knowledge-bases/{knowledge_base_id}/files/{knowledge_file_id}/move",
    operation_id="knowledge_base_files_move",
    response_model=ApiResponse[KnowledgeFileView],
)
async def move_knowledge_file(
    knowledge_base_id: UUID,
    knowledge_file_id: UUID,
    body: KnowledgeFileMove,
    service: Annotated[FileManagementService, Depends(file_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ApiResponse[KnowledgeFileView]:
    async with session.begin():
        result = await service.move_file(
            knowledge_base_id, knowledge_file_id, body.target_knowledge_base_id
        )
    return success_response(result, message="文件已移动")


@router.get(
    "/knowledge-bases/{knowledge_base_id}/files/{knowledge_file_id}/download-url",
    operation_id="knowledge_base_files_download_url",
    response_model=ApiResponse[DownloadUrlView],
)
async def get_download_url(
    knowledge_base_id: UUID,
    knowledge_file_id: UUID,
    service: Annotated[FileManagementService, Depends(file_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ApiResponse[DownloadUrlView]:
    async with session.begin():
        result = await service.download_url(knowledge_base_id, knowledge_file_id)
    return success_response(result)


@router.get(
    "/knowledge-bases/{knowledge_base_id}/files/{knowledge_file_id}/deletion-impact",
    operation_id="knowledge_base_files_deletion_impact",
    response_model=ApiResponse[DeletionImpactView],
)
async def file_deletion_impact(
    knowledge_base_id: UUID,
    knowledge_file_id: UUID,
    service: Annotated[FileManagementService, Depends(file_service)],
    mode: str = Query(default="SOURCE_ONLY", pattern="^(SOURCE_ONLY|CASCADE)$"),
) -> ApiResponse[DeletionImpactView]:
    return success_response(
        await service.file_deletion_impact(knowledge_base_id, knowledge_file_id, mode)
    )


@router.delete(
    "/knowledge-bases/{knowledge_base_id}/files/{knowledge_file_id}",
    operation_id="knowledge_base_files_delete",
    response_model=ApiResponse[DeleteResult],
)
async def delete_knowledge_file(
    knowledge_base_id: UUID,
    knowledge_file_id: UUID,
    body: DeleteRequest,
    service: Annotated[FileManagementService, Depends(file_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ApiResponse[DeleteResult]:
    async with session.begin():
        result = await service.delete_file(
            knowledge_base_id,
            knowledge_file_id,
            body.confirmation_token,
            body.mode,
        )
    return success_response(result, message="文件已删除")


@router.get(
    "/file-policies/effective",
    operation_id="file_policies_effective",
    response_model=ApiResponse[FilePolicyView],
)
async def effective_file_policy(
    session: Annotated[AsyncSession, Depends(database_session)],
    _user: Annotated[User, Depends(current_user_model)],
) -> ApiResponse[FilePolicyView]:
    async with session.begin():
        policy = await FilePolicyService(session).ensure_default()
    return success_response(FilePolicyView.model_validate(policy))


@router.get(
    "/admin/file-policy-versions",
    operation_id="admin_file_policy_versions_list",
    response_model=ApiResponse[list[FilePolicyView]],
)
async def list_file_policy_versions(
    session: Annotated[AsyncSession, Depends(database_session)],
    user: Annotated[User, Depends(current_user_model)],
) -> ApiResponse[list[FilePolicyView]]:
    require_admin(user)
    items = await FilePolicyService(session).list_versions()
    return success_response([FilePolicyView.model_validate(item) for item in items])


@router.post(
    "/admin/file-policy-versions",
    operation_id="admin_file_policy_versions_create",
    response_model=ApiResponse[FilePolicyView],
)
async def create_file_policy_version(
    body: FilePolicyDraftRequest,
    session: Annotated[AsyncSession, Depends(database_session)],
    user: Annotated[User, Depends(current_user_model)],
) -> ApiResponse[FilePolicyView]:
    require_admin(user)
    async with session.begin():
        item = await FilePolicyService(session).create_draft(body.rules, body.base_version_id)
    return success_response(FilePolicyView.model_validate(item), message="文件策略草稿已创建")


@router.patch(
    "/admin/file-policy-versions/{policy_id}",
    operation_id="admin_file_policy_versions_update",
    response_model=ApiResponse[FilePolicyView],
)
async def update_file_policy_version(
    policy_id: UUID,
    body: FilePolicyUpdateRequest,
    session: Annotated[AsyncSession, Depends(database_session)],
    user: Annotated[User, Depends(current_user_model)],
) -> ApiResponse[FilePolicyView]:
    require_admin(user)
    async with session.begin():
        item = await FilePolicyService(session).update_draft(policy_id, body.rules)
    return success_response(FilePolicyView.model_validate(item), message="文件策略草稿已更新")


@router.post(
    "/admin/file-policy-versions/{policy_id}/publish",
    operation_id="admin_file_policy_versions_publish",
    response_model=ApiResponse[FilePolicyView],
)
async def publish_file_policy_version(
    policy_id: UUID,
    body: FilePolicyPublishRequest,
    session: Annotated[AsyncSession, Depends(database_session)],
    user: Annotated[User, Depends(current_user_model)],
) -> ApiResponse[FilePolicyView]:
    require_admin(user)
    async with session.begin():
        item = await FilePolicyService(session).publish(policy_id, body.base_version_id, user.id)
    return success_response(FilePolicyView.model_validate(item), message="文件策略已发布")
