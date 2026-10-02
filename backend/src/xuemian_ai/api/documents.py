from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from xuemian_ai.accounts.models import User
from xuemian_ai.auth.dependencies import current_user_model, database_session
from xuemian_ai.core.config import Settings, get_settings
from xuemian_ai.core.responses import ApiResponse, success_response
from xuemian_ai.document_processing.retrieval import RetrievalService
from xuemian_ai.document_processing.schemas import (
    AIConsentRequest,
    AIConsentView,
    ProcessingTaskView,
    RetrievalRequest,
    RetrievalResult,
)
from xuemian_ai.document_processing.service import DocumentService

router = APIRouter(tags=["document-processing"])


def service(
    session: Annotated[AsyncSession, Depends(database_session)],
    user: Annotated[User, Depends(current_user_model)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentService:
    return DocumentService(session, user, settings)


@router.get(
    "/users/me/ai-processing-consent",
    operation_id="ai_processing_consent_get",
    response_model=ApiResponse[AIConsentView],
)
async def get_consent(
    document: Annotated[DocumentService, Depends(service)],
) -> ApiResponse[AIConsentView]:
    return success_response(await document.consent())


@router.post(
    "/users/me/ai-processing-consent",
    operation_id="ai_processing_consent_confirm",
    response_model=ApiResponse[AIConsentView],
)
async def confirm_consent(
    body: AIConsentRequest,
    document: Annotated[DocumentService, Depends(service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ApiResponse[AIConsentView]:
    async with session.begin():
        result = await document.consent(body.terms_version)
    return success_response(result, message="AI 处理说明已确认")


@router.get(
    "/knowledge-bases/{kb}/files/{file}/processing-task",
    operation_id="document_processing_task_get",
    response_model=ApiResponse[ProcessingTaskView | None],
)
async def get_task(
    kb: UUID, file: UUID, document: Annotated[DocumentService, Depends(service)]
) -> ApiResponse[ProcessingTaskView | None]:
    return success_response(await document.get(kb, file))


@router.post(
    "/knowledge-bases/{kb}/files/{file}/processing-tasks",
    operation_id="document_processing_task_create",
    response_model=ApiResponse[ProcessingTaskView],
)
async def create_task(
    kb: UUID,
    file: UUID,
    document: Annotated[DocumentService, Depends(service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ApiResponse[ProcessingTaskView]:
    async with session.begin():
        result = await document.start(kb, file)
    return success_response(result, message="解析任务已创建")


@router.delete(
    "/knowledge-bases/{kb}/files/{file}/processing-task",
    operation_id="document_processing_task_cancel",
    response_model=ApiResponse[ProcessingTaskView | None],
)
async def cancel_task(
    kb: UUID,
    file: UUID,
    document: Annotated[DocumentService, Depends(service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ApiResponse[ProcessingTaskView | None]:
    async with session.begin():
        result = await document.cancel(kb, file)
    return success_response(result, message="取消请求已处理")


@router.post(
    "/knowledge-bases/{kb}/retrieval/search",
    operation_id="document_retrieval_search",
    response_model=ApiResponse[RetrievalResult],
)
async def search(
    kb: UUID,
    body: RetrievalRequest,
    request: Request,
    response: Response,
    user: Annotated[User, Depends(current_user_model)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApiResponse[RetrievalResult]:
    response.headers["Cache-Control"] = "no-store"
    retrieval = RetrievalService(
        request.app.state.infrastructure.sessions,
        settings,
        user.id,
        getattr(request.state, "request_id", None),
    )
    return success_response(await retrieval.search(kb, body))
