import { authenticatedAccessToken } from "@/features/auth/auth-provider";
import {
  practiceSourcePreview,
  practiceList,
  practiceCreate,
  practiceDetail,
  practicePatch,
  practiceDelete,
  practicePlan,
  practicePlanGet,
  practiceGenerate,
  practiceRevisionGet,
  practiceRegenerate,
  practiceQuestionEdit,
  practiceQuestionDelete,
  practiceAttemptCreate,
  practiceAttemptGet,
  practiceAnswerSave,
  practiceSubmit,
  practiceRegrade,
  practiceGradeGet,
  practiceComplete,
  practiceReport,
  practiceRunGet,
  practiceRunLookup,
  practiceCancel,
  practiceRetry,
  practiceFeedback,
} from "@/lib/api/generated/sdk.gen";
import type {
  SourcePreview,
  SetCreate,
  SetView,
  SetDetail,
  SetPatch,
  PlanRequest,
  GenerateRequest,
  PlanView,
  RevisionView,
  RegenerateRequest,
  QuestionEdit,
  AttemptCreate,
  AttemptView,
  AnswerSave,
  SubmitRequest,
  SubmissionGradeView,
  RegradeRequest,
  GradeView,
  ReportView,
  RunView,
  RetryRequest,
  FeedbackView,
  XuemianAiPracticeSchemasFeedbackRequest as FeedbackRequest,
} from "@/lib/api/generated/types.gen";
import {
  API_BASE_URL,
  requestQueryData,
  requestPageData,
  requestMutation,
  requestNoContent,
} from "@/lib/api/protocol";
export type {
  SetCreate,
  SetView,
  SetDetail,
  SetPatch,
  PlanRequest,
  GenerateRequest,
  PlanView,
  RevisionView,
  RegenerateRequest,
  QuestionEdit,
  AttemptCreate,
  AttemptView,
  AnswerSave,
  SubmitRequest,
  SubmissionGradeView,
  RegradeRequest,
  GradeView,
  ReportView,
  RunView,
  RetryRequest,
  FeedbackView,
  FeedbackRequest,
};
export type {
  PracticeConfig,
  PlanCandidate,
  SourceRef,
  RubricDimension,
} from "@/lib/api/generated/types.gen";
export type PracticeQuestion = QuestionEdit["question"];
export type PracticeAnswer = AnswerSave["answer"];

async function options() {
  const token = await authenticatedAccessToken();
  return {
    baseUrl: API_BASE_URL,
    credentials: "include" as const,
    cache: "no-store" as const,
    throwOnError: true as const,
    headers: { Authorization: `Bearer ${token}` },
  };
}
export async function listPracticeSets(page = 1) {
  const opts = await options();
  return requestPageData<SetView>(() => practiceList({ ...opts, query: { page, page_size: 20 } }));
}
export async function getPracticeSet(id: string) {
  const opts = await options();
  return requestQueryData<SetDetail>(() => practiceDetail({ ...opts, path: { set_id: id } }));
}
export async function createPracticeSet(body: SetCreate) {
  const opts = await options();
  return requestMutation<SetView>(() => practiceCreate({ ...opts, body }));
}
export async function patchPracticeSet(id: string, body: SetPatch) {
  const opts = await options();
  return requestMutation<SetView>(() => practicePatch({ ...opts, path: { set_id: id }, body }));
}
export async function deletePracticeSet(id: string, expectedVersion: number) {
  const opts = await options();
  return requestNoContent(
    () =>
      practiceDelete({
        ...opts,
        path: { set_id: id },
        body: { expected_version: expectedVersion },
      }),
    "练习已删除",
  );
}
export async function getPracticePlan(id: string, version: number) {
  const opts = await options();
  return requestQueryData<PlanView>(() =>
    practicePlanGet({ ...opts, path: { set_id: id, plan_version: version } }),
  );
}
export async function requestPracticePlan(id: string, body: PlanRequest) {
  const opts = await options();
  return requestMutation<RunView>(() => practicePlan({ ...opts, path: { set_id: id }, body }));
}
export async function generatePractice(id: string, body: GenerateRequest) {
  const opts = await options();
  return requestMutation<RunView>(() => practiceGenerate({ ...opts, path: { set_id: id }, body }));
}
export async function getPracticeRevision(id: string, revisionId: string) {
  const opts = await options();
  return requestQueryData<RevisionView>(() =>
    practiceRevisionGet({ ...opts, path: { set_id: id, revision_id: revisionId } }),
  );
}
export async function regeneratePractice(id: string, body: RegenerateRequest) {
  const opts = await options();
  return requestMutation<RunView>(() =>
    practiceRegenerate({ ...opts, path: { set_id: id }, body }),
  );
}
export async function editPracticeQuestion(id: string, questionId: string, body: QuestionEdit) {
  const opts = await options();
  return requestMutation<RevisionView>(() =>
    practiceQuestionEdit({ ...opts, path: { set_id: id, question_id: questionId }, body }),
  );
}
export async function deletePracticeQuestion(
  id: string,
  questionId: string,
  expectedVersion: number,
) {
  const opts = await options();
  return requestMutation<RevisionView>(() =>
    practiceQuestionDelete({
      ...opts,
      path: { set_id: id, question_id: questionId },
      body: { expected_version: expectedVersion },
    }),
  );
}
export async function startPracticeAttempt(id: string, body: AttemptCreate) {
  const opts = await options();
  return requestMutation<AttemptView>(() =>
    practiceAttemptCreate({ ...opts, path: { set_id: id }, body }),
  );
}
export async function getPracticeAttempt(id: string) {
  const opts = await options();
  return requestQueryData<AttemptView>(() =>
    practiceAttemptGet({ ...opts, path: { attempt_id: id } }),
  );
}
export async function savePracticeAnswer(id: string, questionId: string, body: AnswerSave) {
  const opts = await options();
  return requestMutation<AttemptView>(() =>
    practiceAnswerSave({ ...opts, path: { attempt_id: id, question_id: questionId }, body }),
  );
}
export async function submitPracticeAnswer(id: string, questionId: string, body: SubmitRequest) {
  const opts = await options();
  return requestMutation<SubmissionGradeView | RunView>(() =>
    practiceSubmit({ ...opts, path: { attempt_id: id, question_id: questionId }, body }),
  );
}
export async function regradePractice(id: string, body: RegradeRequest) {
  const opts = await options();
  return requestMutation<RunView>(() =>
    practiceRegrade({ ...opts, path: { submission_id: id }, body }),
  );
}
export async function getPracticeGrade(id: string, version: number) {
  const opts = await options();
  return requestQueryData<GradeView>(() =>
    practiceGradeGet({ ...opts, path: { submission_id: id, grade_version: version } }),
  );
}
export async function completePractice(id: string, expectedVersion: number) {
  const opts = await options();
  return requestMutation<AttemptView>(() =>
    practiceComplete({
      ...opts,
      path: { attempt_id: id },
      body: { expected_version: expectedVersion },
    }),
  );
}
export async function getPracticeReport(id: string) {
  const opts = await options();
  return requestQueryData<ReportView>(() => practiceReport({ ...opts, path: { attempt_id: id } }));
}
export async function getPracticeRun(id: string) {
  const opts = await options();
  return requestQueryData<RunView>(() => practiceRunGet({ ...opts, path: { run_id: id } }));
}
export async function lookupPracticeRun(requestKey: string, setId: string) {
  const opts = await options();
  return requestQueryData<RunView>(() =>
    practiceRunLookup({ ...opts, query: { request_key: requestKey, set_id: setId } }),
  );
}
export async function cancelPracticeRun(id: string) {
  const opts = await options();
  return requestMutation<RunView>(() => practiceCancel({ ...opts, path: { run_id: id } }));
}
export async function retryPracticeRun(id: string, body: RetryRequest) {
  const opts = await options();
  return requestMutation<RunView>(() => practiceRetry({ ...opts, path: { run_id: id }, body }));
}
export async function setPracticeFeedback(body: FeedbackRequest) {
  const opts = await options();
  return requestMutation<FeedbackView>(() => practiceFeedback({ ...opts, body }));
}

export async function getPracticeSource(
  setId: string,
  revisionId: string,
  questionId: string,
  sourceId: string,
) {
  const opts = await options();
  return requestQueryData<SourcePreview>(() =>
    practiceSourcePreview({
      ...opts,
      path: {
        set_id: setId,
        revision_id: revisionId,
        question_id: questionId,
        source_id: sourceId,
      },
    }),
  );
}
