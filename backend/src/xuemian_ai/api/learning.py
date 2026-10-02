from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from xuemian_ai.accounts.models import User
from xuemian_ai.auth.dependencies import current_user_model
from xuemian_ai.core.config import Settings, get_settings
from xuemian_ai.core.responses import ApiResponse, PageResponse, success_response
from xuemian_ai.document_processing.schemas import AIConsentRequest, AIConsentView
from xuemian_ai.learning.schemas import (
    AnswerRequest,
    ConversationCreate,
    ConversationDetail,
    ConversationRename,
    ConversationView,
    FeedbackRequest,
    TurnView,
)
from xuemian_ai.learning.service import LearningService


def private_response(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/learning", tags=["learning"], dependencies=[Depends(private_response)])


def service(
    request: Request,
    user: Annotated[User, Depends(current_user_model)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LearningService:
    return LearningService(
        request.app.state.infrastructure.sessions,
        settings,
        user.id,
        getattr(request.state, "request_id", None),
    )


@router.get(
    "/consent", operation_id="learning_consent_get", response_model=ApiResponse[AIConsentView]
)
async def consent_get(
    learning: Annotated[LearningService, Depends(service)],
) -> ApiResponse[AIConsentView]:
    return success_response(await learning.consent())


@router.post(
    "/consent", operation_id="learning_consent_confirm", response_model=ApiResponse[AIConsentView]
)
async def consent_confirm(
    body: AIConsentRequest, learning: Annotated[LearningService, Depends(service)]
) -> ApiResponse[AIConsentView]:
    return success_response(await learning.consent(body.terms_version), message="AI 问答说明已确认")


@router.get(
    "/conversations",
    operation_id="learning_conversations_list",
    response_model=PageResponse[ConversationView],
)
async def list_conversations(
    learning: Annotated[LearningService, Depends(service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PageResponse[ConversationView]:
    return await learning.list_conversations(page, page_size)


@router.post(
    "/conversations",
    operation_id="learning_conversations_create",
    response_model=ApiResponse[ConversationView],
)
async def create_conversation(
    body: ConversationCreate, learning: Annotated[LearningService, Depends(service)]
) -> ApiResponse[ConversationView]:
    return success_response(await learning.create(body))


@router.get(
    "/conversations/{conversation_id}",
    operation_id="learning_conversations_get",
    response_model=ApiResponse[ConversationDetail],
)
async def detail(
    conversation_id: UUID, learning: Annotated[LearningService, Depends(service)]
) -> ApiResponse[ConversationDetail]:
    return success_response(await learning.detail(conversation_id))


@router.patch(
    "/conversations/{conversation_id}",
    operation_id="learning_conversations_rename",
    response_model=ApiResponse[ConversationView],
)
async def rename(
    conversation_id: UUID,
    body: ConversationRename,
    learning: Annotated[LearningService, Depends(service)],
) -> ApiResponse[ConversationView]:
    return success_response(await learning.rename(conversation_id, body.title))


@router.delete(
    "/conversations/{conversation_id}",
    operation_id="learning_conversations_delete",
    response_model=ApiResponse[None],
)
async def delete(
    conversation_id: UUID, learning: Annotated[LearningService, Depends(service)]
) -> ApiResponse[None]:
    await learning.delete(conversation_id)
    return success_response(None, message="会话已删除")


@router.post(
    "/conversations/{conversation_id}/answers",
    operation_id="learning_answers_create",
    response_model=ApiResponse[TurnView],
)
async def answer(
    conversation_id: UUID,
    body: AnswerRequest,
    learning: Annotated[LearningService, Depends(service)],
) -> ApiResponse[TurnView]:
    return success_response(await learning.answer(conversation_id, body))


@router.patch(
    "/conversations/{conversation_id}/turns/{turn_id}/feedback",
    operation_id="learning_answers_feedback",
    response_model=ApiResponse[TurnView],
)
async def feedback(
    conversation_id: UUID,
    turn_id: UUID,
    body: FeedbackRequest,
    learning: Annotated[LearningService, Depends(service)],
) -> ApiResponse[TurnView]:
    return success_response(await learning.feedback(conversation_id, turn_id, body.feedback))
