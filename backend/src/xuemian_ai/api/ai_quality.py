from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from xuemian_ai.accounts.models import User
from xuemian_ai.ai_quality.schemas import (
    AccessRequest,
    AdminCaseDetail,
    AdminMessageCreate,
    AssignmentRequest,
    CaseCreate,
    CaseStatus,
    CaseView,
    Category,
    GrantDecision,
    GrantField,
    GrantRevoke,
    MessageCreate,
    QualityOverview,
    ReplayRequest,
    SnapshotRequest,
    SnapshotView,
    TransitionRequest,
    UserCaseDetail,
    VersionRequest,
)
from xuemian_ai.ai_quality.service import QualityService
from xuemian_ai.auth.dependencies import current_user_model
from xuemian_ai.core.config import Settings, get_settings
from xuemian_ai.core.errors import AppError, ValidationAppError
from xuemian_ai.core.responses import ApiResponse, PageResponse, success_response
from xuemian_ai.core.status_codes import ApiStatusCode


class PrivateRoute(APIRoute):
    def get_route_handler(self) -> Any:
        handler = super().get_route_handler()

        async def private(request: Request) -> Response:
            try:
                response = await handler(request)
                response.headers["Cache-Control"] = "no-store"
                return response
            except RequestValidationError:
                error = ValidationAppError(error_key="QUALITY_INPUT_INVALID")
                error.headers = {**(error.headers or {}), "Cache-Control": "no-store"}
                raise error from None
            except AppError as error:
                error.headers = {**(error.headers or {}), "Cache-Control": "no-store"}
                raise

        return private


router = APIRouter(tags=["ai-quality"], route_class=PrivateRoute)


def service(
    request: Request,
    user: Annotated[User, Depends(current_user_model)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> QualityService:
    return QualityService(
        request.app.state.infrastructure.sessions,
        user,
        settings,
        getattr(request.state, "request_id", None),
    )


async def user_service(domain: Annotated[QualityService, Depends(service)]) -> QualityService:
    async with domain._tx("user_role_check"):
        domain._role(False)
    return domain


async def admin_service(domain: Annotated[QualityService, Depends(service)]) -> QualityService:
    async with domain._tx("admin_role_check"):
        domain._role(True)
    return domain


UserDomain = Annotated[QualityService, Depends(user_service)]
AdminDomain = Annotated[QualityService, Depends(admin_service)]


@router.post(
    "/ai-quality-cases",
    operation_id="quality_case_create",
    status_code=201,
    response_model=ApiResponse[UserCaseDetail],
)
async def create(body: CaseCreate, domain: UserDomain) -> ApiResponse[UserCaseDetail]:
    return success_response(await domain.create(body), code=ApiStatusCode.CREATED)


@router.get(
    "/ai-quality-cases", operation_id="quality_case_list", response_model=PageResponse[CaseView]
)
async def user_list(
    domain: UserDomain,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status: CaseStatus | None = None,
) -> PageResponse[CaseView]:
    return await domain.list_cases(False, page, page_size, status=status)


@router.get(
    "/ai-quality-cases/{case_id}",
    operation_id="quality_case_detail",
    response_model=ApiResponse[UserCaseDetail],
)
async def user_detail(case_id: UUID, domain: UserDomain) -> ApiResponse[UserCaseDetail]:
    return success_response(await domain.user_detail(case_id))


@router.post(
    "/ai-quality-cases/{case_id}/messages",
    operation_id="quality_case_message",
    response_model=ApiResponse[UserCaseDetail],
)
async def user_message(
    case_id: UUID, body: MessageCreate, domain: UserDomain
) -> ApiResponse[UserCaseDetail]:
    return success_response(await domain.user_message(case_id, body))


@router.post(
    "/ai-quality-cases/{case_id}/grants/{grant_id}/decision",
    operation_id="quality_grant_decision",
    response_model=ApiResponse[UserCaseDetail],
)
async def grant_decision(
    case_id: UUID, grant_id: UUID, body: GrantDecision, domain: UserDomain
) -> ApiResponse[UserCaseDetail]:
    return success_response(await domain.grant_decision(case_id, grant_id, body))


@router.delete(
    "/ai-quality-cases/{case_id}/grants/{grant_id}",
    operation_id="quality_grant_revoke",
    response_model=ApiResponse[UserCaseDetail],
)
async def grant_revoke(
    case_id: UUID, grant_id: UUID, body: GrantRevoke, domain: UserDomain
) -> ApiResponse[UserCaseDetail]:
    return success_response(await domain.grant_revoke(case_id, grant_id, body))


@router.delete(
    "/ai-quality-cases/{case_id}",
    operation_id="quality_case_withdraw",
    response_model=ApiResponse[UserCaseDetail],
)
async def withdraw(
    case_id: UUID, body: VersionRequest, domain: UserDomain
) -> ApiResponse[UserCaseDetail]:
    return success_response(await domain.user_close(case_id, body.expected_version, True))


@router.post(
    "/ai-quality-cases/{case_id}/close",
    operation_id="quality_case_close",
    response_model=ApiResponse[UserCaseDetail],
)
async def close(
    case_id: UUID, body: VersionRequest, domain: UserDomain
) -> ApiResponse[UserCaseDetail]:
    return success_response(await domain.user_close(case_id, body.expected_version))


@router.get(
    "/admin/ai-quality/overview",
    operation_id="quality_admin_overview",
    response_model=ApiResponse[QualityOverview],
)
async def overview(domain: AdminDomain) -> ApiResponse[QualityOverview]:
    return success_response(await domain.overview())


@router.get(
    "/admin/ai-quality/cases",
    operation_id="quality_admin_queue",
    response_model=PageResponse[CaseView],
)
async def queue(
    domain: AdminDomain,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status: CaseStatus | None = None,
    category: Category | None = None,
    source_type: Literal["learning_turn"] | None = None,
    strategy_version: str | None = None,
    assignee_id: UUID | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    sort: Literal["oldest", "updated", "newest"] = "oldest",
) -> PageResponse[CaseView]:
    return await domain.list_cases(
        True,
        page,
        page_size,
        status,
        category,
        source_type,
        strategy_version,
        assignee_id,
        created_after,
        created_before,
        sort,
    )


@router.get(
    "/admin/ai-quality/cases/{case_id}",
    operation_id="quality_admin_detail",
    response_model=ApiResponse[AdminCaseDetail],
)
async def admin_detail(case_id: UUID, domain: AdminDomain) -> ApiResponse[AdminCaseDetail]:
    return success_response(await domain.admin_detail(case_id))


@router.get(
    "/admin/ai-quality/cases/{case_id}/snapshot",
    operation_id="quality_admin_snapshot",
    response_model=ApiResponse[SnapshotView],
)
async def snapshot(
    case_id: UUID,
    domain: AdminDomain,
    grant_id: UUID,
    expected_grant_version: Annotated[int, Query(ge=1)],
    fields: Annotated[list[GrantField], Query(min_length=1, max_length=4)],
) -> ApiResponse[SnapshotView]:
    return success_response(
        await domain.snapshot(
            case_id,
            SnapshotRequest(
                grant_id=grant_id,
                expected_grant_version=expected_grant_version,
                fields=fields,
            ),
        )
    )


@router.post(
    "/admin/ai-quality/cases/{case_id}/assign",
    operation_id="quality_admin_assign",
    response_model=ApiResponse[AdminCaseDetail],
)
async def assign(
    case_id: UUID, body: AssignmentRequest, domain: AdminDomain
) -> ApiResponse[AdminCaseDetail]:
    return success_response(await domain.assign(case_id, body))


@router.post(
    "/admin/ai-quality/cases/{case_id}/access-requests",
    operation_id="quality_admin_access_request",
    response_model=ApiResponse[AdminCaseDetail],
)
async def access_request(
    case_id: UUID, body: AccessRequest, domain: AdminDomain
) -> ApiResponse[AdminCaseDetail]:
    return success_response(await domain.access_request(case_id, body))


@router.post(
    "/admin/ai-quality/cases/{case_id}/replays",
    operation_id="quality_admin_replay",
    response_model=ApiResponse[AdminCaseDetail],
)
async def replay(
    case_id: UUID, body: ReplayRequest, domain: AdminDomain
) -> ApiResponse[AdminCaseDetail]:
    return success_response(await domain.replay(case_id, body))


@router.post(
    "/admin/ai-quality/cases/{case_id}/messages",
    operation_id="quality_admin_message",
    response_model=ApiResponse[AdminCaseDetail],
)
async def admin_message(
    case_id: UUID, body: AdminMessageCreate, domain: AdminDomain
) -> ApiResponse[AdminCaseDetail]:
    return success_response(await domain.admin_message(case_id, body))


@router.post(
    "/admin/ai-quality/cases/{case_id}/transitions",
    operation_id="quality_admin_transition",
    response_model=ApiResponse[AdminCaseDetail],
)
async def transition(
    case_id: UUID, body: TransitionRequest, domain: AdminDomain
) -> ApiResponse[AdminCaseDetail]:
    return success_response(await domain.transition(case_id, body))
