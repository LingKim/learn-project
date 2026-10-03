from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from xuemian_ai.accounts.models import User
from xuemian_ai.auth.dependencies import current_user_model
from xuemian_ai.core.config import Settings, get_settings
from xuemian_ai.core.responses import ApiResponse, PageResponse, success_response
from xuemian_ai.core.status_codes import ApiStatusCode
from xuemian_ai.practice.schemas import (
    AnswerSave,
    AttemptCreate,
    AttemptView,
    FeedbackRequest,
    FeedbackView,
    GenerateRequest,
    GradeView,
    PlanRequest,
    PlanView,
    QuestionEdit,
    RegenerateRequest,
    RegradeRequest,
    ReportView,
    RetryRequest,
    RevisionView,
    RunView,
    SetCreate,
    SetDetail,
    SetPatch,
    SetView,
    SourcePreview,
    SubmissionGradeView,
    SubmitRequest,
    VersionRequest,
)
from xuemian_ai.practice.service import PracticeService


def private_response(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/learning/practice", tags=["practice"], dependencies=[Depends(private_response)]
)


def service(
    request: Request,
    user: Annotated[User, Depends(current_user_model)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PracticeService:
    return PracticeService(request.app.state.infrastructure.sessions, user.id, settings)


Domain = Annotated[PracticeService, Depends(service)]


@router.post(
    "/sets", operation_id="practice_create", response_model=ApiResponse[SetView], status_code=201
)
async def create(body: SetCreate, domain: Domain) -> ApiResponse[SetView]:
    return success_response(await domain.create(body), code=ApiStatusCode.CREATED)


@router.get(
    "/sets/{set_id}",
    operation_id="practice_detail",
    response_model=ApiResponse[SetDetail],
    status_code=200,
)
async def detail(set_id: UUID, domain: Domain) -> ApiResponse[SetDetail]:
    return success_response(await domain.detail(set_id), code=ApiStatusCode.OK)


@router.patch(
    "/sets/{set_id}",
    operation_id="practice_patch",
    response_model=ApiResponse[SetView],
    status_code=200,
)
async def patch(set_id: UUID, body: SetPatch, domain: Domain) -> ApiResponse[SetView]:
    return success_response(await domain.patch(set_id, body), code=ApiStatusCode.OK)


@router.get(
    "/sets/{set_id}/plans/{plan_version}",
    operation_id="practice_plan_get",
    response_model=ApiResponse[PlanView],
    status_code=200,
)
async def plan_get(set_id: UUID, plan_version: int, domain: Domain) -> ApiResponse[PlanView]:
    return success_response(await domain.get_plan(set_id, plan_version), code=ApiStatusCode.OK)


@router.get(
    "/sets/{set_id}/revisions/{revision_id}",
    operation_id="practice_revision_get",
    response_model=ApiResponse[RevisionView],
    status_code=200,
)
async def revision_get(
    set_id: UUID, revision_id: UUID, domain: Domain
) -> ApiResponse[RevisionView]:
    return success_response(await domain.get_revision(set_id, revision_id), code=ApiStatusCode.OK)


@router.post(
    "/sets/{set_id}/plan",
    operation_id="practice_plan",
    response_model=ApiResponse[RunView],
    status_code=202,
)
async def plan(set_id: UUID, body: PlanRequest, domain: Domain) -> ApiResponse[RunView]:
    return success_response(await domain.plan(set_id, body), code=ApiStatusCode.ACCEPTED)


@router.post(
    "/sets/{set_id}/generate",
    operation_id="practice_generate",
    response_model=ApiResponse[RunView],
    status_code=202,
)
async def generate(set_id: UUID, body: GenerateRequest, domain: Domain) -> ApiResponse[RunView]:
    return success_response(await domain.generate(set_id, body), code=ApiStatusCode.ACCEPTED)


@router.post(
    "/sets/{set_id}/regenerate",
    operation_id="practice_regenerate",
    response_model=ApiResponse[RunView],
    status_code=202,
)
async def regenerate(set_id: UUID, body: RegenerateRequest, domain: Domain) -> ApiResponse[RunView]:
    return success_response(await domain.regenerate(set_id, body), code=ApiStatusCode.ACCEPTED)


@router.patch(
    "/sets/{set_id}/questions/{question_id}",
    operation_id="practice_question_edit",
    response_model=ApiResponse[RevisionView],
    status_code=200,
)
async def question_edit(
    set_id: UUID, question_id: UUID, body: QuestionEdit, domain: Domain
) -> ApiResponse[RevisionView]:
    return success_response(
        await domain.edit_question(set_id, question_id, body.expected_version, body.question),
        code=ApiStatusCode.OK,
    )


@router.delete(
    "/sets/{set_id}/questions/{question_id}",
    operation_id="practice_question_delete",
    response_model=ApiResponse[RevisionView],
    status_code=200,
)
async def question_delete(
    set_id: UUID, question_id: UUID, body: VersionRequest, domain: Domain
) -> ApiResponse[RevisionView]:
    return success_response(
        await domain.edit_question(set_id, question_id, body.expected_version, None),
        code=ApiStatusCode.OK,
    )


@router.post(
    "/sets/{set_id}/attempts",
    operation_id="practice_attempt_create",
    response_model=ApiResponse[AttemptView],
    status_code=201,
)
async def attempt_create(
    set_id: UUID, body: AttemptCreate, domain: Domain
) -> ApiResponse[AttemptView]:
    return success_response(await domain.create_attempt(set_id, body), code=ApiStatusCode.CREATED)


@router.get(
    "/attempts/{attempt_id}",
    operation_id="practice_attempt_get",
    response_model=ApiResponse[AttemptView],
    status_code=200,
)
async def attempt_get(attempt_id: UUID, domain: Domain) -> ApiResponse[AttemptView]:
    return success_response(await domain.get_attempt(attempt_id), code=ApiStatusCode.OK)


@router.patch(
    "/attempts/{attempt_id}/answers/{question_id}",
    operation_id="practice_answer_save",
    response_model=ApiResponse[AttemptView],
    status_code=200,
)
async def answer_save(
    attempt_id: UUID, question_id: UUID, body: AnswerSave, domain: Domain
) -> ApiResponse[AttemptView]:
    return success_response(
        await domain.save_answer(attempt_id, question_id, body), code=ApiStatusCode.OK
    )


@router.post(
    "/submissions/{submission_id}/regrade",
    operation_id="practice_regrade",
    response_model=ApiResponse[RunView],
    status_code=202,
)
async def regrade(
    submission_id: UUID, body: RegradeRequest, domain: Domain
) -> ApiResponse[RunView]:
    return success_response(await domain.regrade(submission_id, body), code=ApiStatusCode.ACCEPTED)


@router.get(
    "/submissions/{submission_id}/grades/{grade_version}",
    operation_id="practice_grade_get",
    response_model=ApiResponse[GradeView],
    status_code=200,
)
async def grade_get(
    submission_id: UUID, grade_version: int, domain: Domain
) -> ApiResponse[GradeView]:
    return success_response(
        await domain.get_grade(submission_id, grade_version), code=ApiStatusCode.OK
    )


@router.post(
    "/attempts/{attempt_id}/complete",
    operation_id="practice_complete",
    response_model=ApiResponse[AttemptView],
    status_code=200,
)
async def complete(
    attempt_id: UUID, body: VersionRequest, domain: Domain
) -> ApiResponse[AttemptView]:
    return success_response(
        await domain.complete(attempt_id, body.expected_version), code=ApiStatusCode.OK
    )


@router.get(
    "/attempts/{attempt_id}/report",
    operation_id="practice_report",
    response_model=ApiResponse[ReportView],
    status_code=200,
)
async def report(attempt_id: UUID, domain: Domain) -> ApiResponse[ReportView]:
    return success_response(await domain.report(attempt_id), code=ApiStatusCode.OK)


@router.get(
    "/runs/{run_id}",
    operation_id="practice_run_get",
    response_model=ApiResponse[RunView],
    status_code=200,
)
async def run_get(run_id: UUID, domain: Domain) -> ApiResponse[RunView]:
    return success_response(await domain.get_run(run_id), code=ApiStatusCode.OK)


@router.post(
    "/runs/{run_id}/cancel",
    operation_id="practice_cancel",
    response_model=ApiResponse[RunView],
    status_code=200,
)
async def cancel(run_id: UUID, domain: Domain) -> ApiResponse[RunView]:
    return success_response(await domain.cancel(run_id), code=ApiStatusCode.OK)


@router.post(
    "/runs/{run_id}/retry",
    operation_id="practice_retry",
    response_model=ApiResponse[RunView],
    status_code=202,
)
async def retry(run_id: UUID, body: RetryRequest, domain: Domain) -> ApiResponse[RunView]:
    return success_response(await domain.retry(run_id, body), code=ApiStatusCode.ACCEPTED)


@router.patch(
    "/feedback",
    operation_id="practice_feedback",
    response_model=ApiResponse[FeedbackView],
    status_code=200,
)
async def feedback(body: FeedbackRequest, domain: Domain) -> ApiResponse[FeedbackView]:
    return success_response(await domain.feedback(body), code=ApiStatusCode.OK)


@router.get("/sets", operation_id="practice_list", response_model=PageResponse[SetView])
async def list_sets(
    domain: Domain,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PageResponse[SetView]:
    return await domain.list_sets(page, page_size)


@router.delete("/sets/{set_id}", operation_id="practice_delete", status_code=204)
async def delete(set_id: UUID, body: VersionRequest, domain: Domain) -> Response:
    await domain.delete(set_id, body.expected_version)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/runs", operation_id="practice_run_lookup", response_model=ApiResponse[RunView])
async def run_lookup(
    domain: Domain,
    request_key: UUID,
    operation: Literal["plan", "generate", "regenerate", "grade", "regrade"] | None = None,
    set_id: UUID | None = None,
) -> ApiResponse[RunView]:
    return success_response(await domain.lookup_run(request_key, operation, set_id))


@router.post(
    "/attempts/{attempt_id}/questions/{question_id}/submit",
    operation_id="practice_submit",
    response_model=ApiResponse[SubmissionGradeView] | ApiResponse[RunView],
    responses={202: {"model": ApiResponse[RunView]}},
)
async def submit(
    attempt_id: UUID, question_id: UUID, body: SubmitRequest, response: Response, domain: Domain
) -> ApiResponse[SubmissionGradeView] | ApiResponse[RunView]:
    result = await domain.submit(attempt_id, question_id, body)
    if isinstance(result, RunView):
        response.status_code = 202
        return success_response(result, code=ApiStatusCode.ACCEPTED)
    return success_response(result)


@router.get(
    "/sets/{set_id}/revisions/{revision_id}/questions/{question_id}/sources/{source_id}",
    operation_id="practice_source_preview",
    response_model=ApiResponse[SourcePreview],
)
async def source_preview(
    set_id: UUID, revision_id: UUID, question_id: UUID, source_id: str, domain: Domain
) -> ApiResponse[SourcePreview]:
    return success_response(
        await domain.source_preview(set_id, revision_id, question_id, source_id)
    )
