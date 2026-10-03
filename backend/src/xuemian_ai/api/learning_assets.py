from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from xuemian_ai.accounts.models import User
from xuemian_ai.auth.dependencies import current_user_model
from xuemian_ai.core.config import Settings, get_settings
from xuemian_ai.core.errors import NotFoundError
from xuemian_ai.core.responses import ApiResponse, PageResponse, success_response
from xuemian_ai.core.status_codes import ApiStatusCode
from xuemian_ai.learning_assets.schemas import (
    ConfirmRequest,
    Decision,
    ExplanationAccepted,
    ExplanationCreate,
    ExplanationDetail,
    ExplanationRegenerate,
    ExplanationView,
    KnowledgeCardView,
    KnowledgeRunView,
    LearningReviewView,
    MasteryRequest,
    MasteryState,
    Severity,
    VersionRequest,
    WeaknessCreate,
    WeaknessDetail,
    WeaknessPatch,
    WeaknessView,
)
from xuemian_ai.learning_assets.service import LearningAssetService
from xuemian_ai.practice.schemas import RetryRequest, SourcePreview


def private_response(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(tags=["learning-assets"], dependencies=[Depends(private_response)])


def service(
    request: Request,
    user: Annotated[User, Depends(current_user_model)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LearningAssetService:
    if user.role != "user":
        raise NotFoundError(error_key="LEARNING_ASSET_NOT_FOUND")
    return LearningAssetService(request.app.state.infrastructure.sessions, user.id, settings)


Domain = Annotated[LearningAssetService, Depends(service)]


@router.post(
    "/weaknesses",
    operation_id="weakness_create",
    response_model=ApiResponse[WeaknessView],
    status_code=201,
)
async def create(body: WeaknessCreate, domain: Domain) -> ApiResponse[WeaknessView]:
    return success_response(await domain.create(body), code=ApiStatusCode.CREATED)


@router.get("/weaknesses", operation_id="weakness_list", response_model=PageResponse[WeaknessView])
async def list_weaknesses(
    domain: Domain,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    query: str | None = None,
    tags: Annotated[list[str] | None, Query()] = None,
    tag: str | None = None,
    domain_filter: Annotated[str | None, Query(alias="domain")] = None,
    source_mode: str | None = None,
    severity: Severity | None = None,
    mastery_state: MasteryState | None = None,
    decision: Decision = "confirmed",
) -> PageResponse[WeaknessView]:
    return await domain.list_weaknesses(
        page,
        page_size,
        query,
        tags or ([tag] if tag else None),
        severity,
        mastery_state,
        decision,
        domain_filter,
        source_mode,
    )


@router.get(
    "/weaknesses/{object_id}",
    operation_id="weakness_detail",
    response_model=ApiResponse[WeaknessDetail],
)
async def detail(object_id: UUID, domain: Domain) -> ApiResponse[WeaknessDetail]:
    return success_response(await domain.detail(object_id))


@router.patch(
    "/weaknesses/{object_id}",
    operation_id="weakness_patch",
    response_model=ApiResponse[WeaknessView],
)
async def patch(object_id: UUID, body: WeaknessPatch, domain: Domain) -> ApiResponse[WeaknessView]:
    return success_response(await domain.patch(object_id, body))


@router.post(
    "/weaknesses/{object_id}/confirm",
    operation_id="weakness_confirm",
    response_model=ApiResponse[WeaknessView],
)
async def confirm(
    object_id: UUID, body: ConfirmRequest, domain: Domain
) -> ApiResponse[WeaknessView]:
    return success_response(
        await domain.decide(object_id, body.expected_version, "confirmed", body.request_key)
    )


@router.post(
    "/weaknesses/{object_id}/ignore",
    operation_id="weakness_ignore",
    response_model=ApiResponse[WeaknessView],
)
async def ignore(
    object_id: UUID, body: VersionRequest, domain: Domain
) -> ApiResponse[WeaknessView]:
    return success_response(await domain.decide(object_id, body.expected_version, "ignored"))


@router.post(
    "/weaknesses/{object_id}/revoke",
    operation_id="weakness_revoke",
    response_model=ApiResponse[WeaknessView],
)
async def revoke(
    object_id: UUID, body: VersionRequest, domain: Domain
) -> ApiResponse[WeaknessView]:
    return success_response(await domain.decide(object_id, body.expected_version, "revoked"))


@router.patch(
    "/weaknesses/{object_id}/mastery",
    operation_id="weakness_mastery",
    response_model=ApiResponse[WeaknessView],
)
async def mastery(
    object_id: UUID, body: MasteryRequest, domain: Domain
) -> ApiResponse[WeaknessView]:
    return success_response(await domain.mastery(object_id, body))


@router.delete("/weaknesses/{object_id}", operation_id="weakness_delete", status_code=204)
async def delete(object_id: UUID, body: VersionRequest, domain: Domain) -> Response:
    await domain.delete(object_id, body.expected_version)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get(
    "/weaknesses/{object_id}/reviews",
    operation_id="weakness_reviews",
    response_model=PageResponse[LearningReviewView],
)
async def reviews(
    object_id: UUID,
    domain: Domain,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PageResponse[LearningReviewView]:
    return await domain.reviews(object_id, page, page_size)


@router.post(
    "/learning/explanations",
    operation_id="explanation_create",
    response_model=ApiResponse[ExplanationAccepted],
    status_code=202,
)
async def create_explanation(
    body: ExplanationCreate, domain: Domain
) -> ApiResponse[ExplanationAccepted]:
    return success_response(await domain.create_explanation(body), code=ApiStatusCode.ACCEPTED)


@router.get(
    "/learning/explanations",
    operation_id="explanation_list",
    response_model=PageResponse[ExplanationView],
)
async def list_explanations(
    domain: Domain,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PageResponse[ExplanationView]:
    return await domain.list_explanations(page, page_size)


@router.get(
    "/learning/explanations/{object_id}",
    operation_id="explanation_detail",
    response_model=ApiResponse[ExplanationDetail],
)
async def explanation_detail(object_id: UUID, domain: Domain) -> ApiResponse[ExplanationDetail]:
    return success_response(await domain.explanation_detail(object_id))


@router.get(
    "/learning/explanations/{object_id}/cards/{version}",
    operation_id="explanation_card",
    response_model=ApiResponse[KnowledgeCardView],
)
async def get_card(object_id: UUID, version: int, domain: Domain) -> ApiResponse[KnowledgeCardView]:
    return success_response(await domain.get_card(object_id, version))


@router.get(
    "/learning/explanations/{object_id}/cards/{version}/sources/{source_id}",
    operation_id="explanation_source_preview",
    response_model=ApiResponse[SourcePreview],
)
async def source_preview(
    object_id: UUID, version: int, source_id: str, domain: Domain
) -> ApiResponse[SourcePreview]:
    return success_response(await domain.source_preview(object_id, version, source_id))


@router.post(
    "/learning/explanations/{object_id}/regenerate",
    operation_id="explanation_regenerate",
    response_model=ApiResponse[ExplanationAccepted],
    status_code=202,
)
async def regenerate(
    object_id: UUID, body: ExplanationRegenerate, domain: Domain
) -> ApiResponse[ExplanationAccepted]:
    return success_response(await domain.regenerate(object_id, body), code=ApiStatusCode.ACCEPTED)


@router.delete(
    "/learning/explanations/{object_id}", operation_id="explanation_delete", status_code=204
)
async def delete_explanation(object_id: UUID, body: VersionRequest, domain: Domain) -> Response:
    await domain.delete_explanation(object_id, body.expected_version)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get(
    "/learning/knowledge-runs",
    operation_id="knowledge_run_lookup",
    response_model=ApiResponse[KnowledgeRunView],
)
async def lookup_run(request_key: UUID, domain: Domain) -> ApiResponse[KnowledgeRunView]:
    return success_response(await domain.lookup_run(request_key))


@router.get(
    "/learning/knowledge-runs/{run_id}",
    operation_id="knowledge_run_get",
    response_model=ApiResponse[KnowledgeRunView],
)
async def get_run(run_id: UUID, domain: Domain) -> ApiResponse[KnowledgeRunView]:
    return success_response(await domain.get_run(run_id))


@router.post(
    "/learning/knowledge-runs/{run_id}/cancel",
    operation_id="knowledge_run_cancel",
    response_model=ApiResponse[KnowledgeRunView],
)
async def cancel(run_id: UUID, domain: Domain) -> ApiResponse[KnowledgeRunView]:
    return success_response(await domain.cancel(run_id))


@router.post(
    "/learning/knowledge-runs/{run_id}/retry",
    operation_id="knowledge_run_retry",
    response_model=ApiResponse[KnowledgeRunView],
    status_code=202,
)
async def retry(run_id: UUID, body: RetryRequest, domain: Domain) -> ApiResponse[KnowledgeRunView]:
    return success_response(
        await domain.retry(run_id, body.request_key, body.input_digest), code=ApiStatusCode.ACCEPTED
    )


@router.get(
    "/learning/explanations/{object_id}/reviews",
    operation_id="explanation_reviews",
    response_model=PageResponse[LearningReviewView],
)
async def explanation_reviews(
    object_id: UUID,
    domain: Domain,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PageResponse[LearningReviewView]:
    return await domain.explanation_reviews(object_id, page, page_size)
