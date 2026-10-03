"""管理员边界在读取对象前检查；敏感响应（含失败）不允许浏览器缓存。"""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.routing import APIRoute

from xuemian_ai.accounts.models import User
from xuemian_ai.auth.dependencies import current_user_model
from xuemian_ai.core.config import Settings, get_settings
from xuemian_ai.core.errors import ForbiddenError
from xuemian_ai.core.responses import ApiResponse, PageResponse, success_response
from xuemian_ai.prompt_management.models import PromptAuditEvent
from xuemian_ai.prompt_management.schemas import (
    AuditView,
    DefinitionView,
    DiffView,
    DraftCreate,
    DraftPatch,
    EvaluationView,
    PreviewRequest,
    PreviewView,
    PublishRequest,
    RollbackRequest,
    StatusRequest,
    VersionSummary,
    VersionView,
)
from xuemian_ai.prompt_management.service import PromptService


class PrivateAdminRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                response = await original(request)
            except Exception as exc:
                # 正文不进入审计。即使对象不存在或参数错误，也不暴露响应缓存。
                async with request.app.state.infrastructure.sessions.begin() as session:
                    session.add(
                        PromptAuditEvent(
                            actor_user_id=getattr(request.state, "prompt_actor", None),
                            action="request_denied",
                            outcome="denied",
                            target_id=None,
                            version=None,
                            request_id=str(getattr(request.state, "request_id", ""))[:128],
                        )
                    )
                handler = next(
                    (
                        request.app.exception_handlers[cls]
                        for cls in type(exc).__mro__
                        if cls in request.app.exception_handlers
                    ),
                    None,
                )
                if handler is None:
                    raise
                response = await handler(request, exc)
            response.headers["Cache-Control"] = "no-store"
            return response

        return handle


router = APIRouter(prefix="/admin", tags=["prompts"], route_class=PrivateAdminRoute)


def service(
    request: Request,
    user: Annotated[User, Depends(current_user_model)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PromptService:
    request.state.prompt_actor = user.id
    if user.role != "admin":
        raise ForbiddenError(error_key="PROMPT_ADMIN_REQUIRED")
    return PromptService(
        request.app.state.infrastructure.sessions,
        user.id,
        settings,
        str(getattr(request.state, "request_id", "")),
    )


Domain = Annotated[PromptService, Depends(service)]
Page = Annotated[int, Query(ge=1)]
Size = Annotated[int, Query(ge=1, le=100)]


@router.get(
    "/prompt-definitions",
    operation_id="prompt_definitions_list",
    response_model=PageResponse[DefinitionView],
)
async def definitions(
    domain: Domain,
    page: Page = 1,
    page_size: Size = 20,
    agent_key: str | None = None,
    scene_key: str | None = None,
    template_kind: str | None = None,
    runtime_status: str | None = None,
) -> PageResponse[DefinitionView]:
    return await domain.list_definitions(
        page,
        page_size,
        agent_key=agent_key,
        scene_key=scene_key,
        template_kind=template_kind,
        runtime_status=runtime_status,
    )


@router.get(
    "/prompt-definitions/{definition_id}",
    operation_id="prompt_definition_get",
    response_model=ApiResponse[DefinitionView],
)
async def definition(definition_id: UUID, domain: Domain) -> ApiResponse[DefinitionView]:
    return success_response(await domain.definition(definition_id))


@router.get(
    "/prompt-definitions/{definition_id}/versions",
    operation_id="prompt_versions_list",
    response_model=PageResponse[VersionSummary],
)
async def versions(
    definition_id: UUID, domain: Domain, page: Page = 1, page_size: Size = 20
) -> PageResponse[VersionSummary]:
    return await domain.versions(definition_id, page, page_size)


@router.get(
    "/prompt-versions/{version_id}",
    operation_id="prompt_version_get",
    response_model=ApiResponse[VersionView],
)
async def version(version_id: UUID, domain: Domain) -> ApiResponse[VersionView]:
    return success_response(await domain.version(version_id))


@router.post(
    "/prompt-definitions/{definition_id}/versions",
    operation_id="prompt_draft_create",
    response_model=ApiResponse[VersionView],
    status_code=201,
)
async def create(
    definition_id: UUID, body: DraftCreate, domain: Domain
) -> ApiResponse[VersionView]:
    from xuemian_ai.core.status_codes import ApiStatusCode

    return success_response(
        await domain.create_draft(definition_id, body), code=ApiStatusCode.CREATED
    )


@router.patch(
    "/prompt-versions/{version_id}",
    operation_id="prompt_draft_patch",
    response_model=ApiResponse[VersionView],
)
async def patch(version_id: UUID, body: DraftPatch, domain: Domain) -> ApiResponse[VersionView]:
    return success_response(await domain.patch(version_id, body))


@router.get(
    "/prompt-versions/{version_id}/diff",
    operation_id="prompt_version_diff",
    response_model=ApiResponse[DiffView],
)
async def diff(
    version_id: UUID, domain: Domain, base_version_id: UUID | None = None
) -> ApiResponse[DiffView]:
    return success_response(await domain.diff(version_id, base_version_id))


@router.post(
    "/prompt-versions/{version_id}/preview",
    operation_id="prompt_version_preview",
    response_model=ApiResponse[PreviewView],
)
async def preview(
    version_id: UUID, body: PreviewRequest, domain: Domain
) -> ApiResponse[PreviewView]:
    return success_response(await domain.preview(version_id, body))


@router.post(
    "/prompt-versions/{version_id}/evaluation-runs",
    operation_id="prompt_evaluation_run",
    response_model=ApiResponse[EvaluationView],
)
async def evaluate(version_id: UUID, domain: Domain) -> ApiResponse[EvaluationView]:
    return success_response(await domain.evaluate(version_id))


@router.post(
    "/prompt-versions/{version_id}/publish",
    operation_id="prompt_version_publish",
    response_model=ApiResponse[VersionView],
)
async def publish(
    version_id: UUID, body: PublishRequest, domain: Domain
) -> ApiResponse[VersionView]:
    return success_response(await domain.publish(version_id, body))


@router.post(
    "/prompt-definitions/{definition_id}/rollbacks",
    operation_id="prompt_definition_rollback",
    response_model=ApiResponse[VersionView],
)
async def rollback(
    definition_id: UUID, body: RollbackRequest, domain: Domain
) -> ApiResponse[VersionView]:
    return success_response(await domain.rollback(definition_id, body))


@router.post(
    "/prompt-definitions/{definition_id}/status",
    operation_id="prompt_definition_status",
    response_model=ApiResponse[DefinitionView],
)
async def status(
    definition_id: UUID, body: StatusRequest, domain: Domain
) -> ApiResponse[DefinitionView]:
    return success_response(await domain.status(definition_id, body))


@router.get(
    "/prompt-definitions/{definition_id}/audit-events",
    operation_id="prompt_audit_list",
    response_model=PageResponse[AuditView],
)
async def audits(
    definition_id: UUID, domain: Domain, page: Page = 1, page_size: Size = 20
) -> PageResponse[AuditView]:
    return await domain.audits(definition_id, page, page_size)
