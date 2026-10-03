from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile

from xuemian_ai.accounts.models import User
from xuemian_ai.auth.dependencies import current_user_model
from xuemian_ai.core.config import Settings, get_settings
from xuemian_ai.core.responses import ApiResponse, success_response
from xuemian_ai.learning.attachment_schemas import LearningAttachmentView
from xuemian_ai.learning.attachments import AttachmentService

router = APIRouter(prefix="/learning/attachments", tags=["learning"])


def service(
    request: Request,
    user: Annotated[User, Depends(current_user_model)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AttachmentService:
    return AttachmentService(
        request.app.state.infrastructure.sessions,
        settings,
        user.id,
        request.app.state.infrastructure.object_storage,
    )


@router.post(
    "",
    operation_id="learning_attachments_upload",
    response_model=ApiResponse[LearningAttachmentView],
)
async def upload(
    response: Response,
    attachments: Annotated[AttachmentService, Depends(service)],
    file: Annotated[UploadFile, File()],
) -> ApiResponse[LearningAttachmentView]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return success_response(await attachments.upload(file))
    finally:
        await file.close()


@router.delete(
    "/{attachment_id}", operation_id="learning_attachments_delete", response_model=ApiResponse[None]
)
async def delete(
    attachment_id: UUID,
    response: Response,
    attachments: Annotated[AttachmentService, Depends(service)],
) -> ApiResponse[None]:
    response.headers["Cache-Control"] = "no-store"
    await attachments.delete(attachment_id)
    return success_response(None, message="附件已移除")


@router.get(
    "/{attachment_id}/content",
    operation_id="learning_attachments_content",
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            }
        }
    },
)
async def content(
    attachment_id: UUID, attachments: Annotated[AttachmentService, Depends(service)]
) -> Response:
    payload, mime, filename = await attachments.content(attachment_id)
    return Response(
        payload,
        media_type=mime,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )
