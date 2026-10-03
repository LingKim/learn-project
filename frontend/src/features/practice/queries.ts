import { mutationOptions, queryOptions, type QueryClient } from "@tanstack/react-query";
import * as api from "./api";

export const practiceKeys = {
  all: ["practice"] as const,
  lists: () => ["practice", "sets", "list"] as const,
  list: (page: number) => [...practiceKeys.lists(), page] as const,
  set: (id: string) => ["practice", "sets", id] as const,
  plan: (id: string, version: number) => ["practice", "plans", id, version] as const,
  revision: (id: string, revision: string) => ["practice", "revisions", id, revision] as const,
  attempt: (id: string) => ["practice", "attempts", id] as const,
  report: (id: string) => ["practice", "reports", id] as const,
  grade: (id: string, version: number) => ["practice", "grades", id, version] as const,
  run: (id: string) => ["practice", "runs", id] as const,
  lookup: (setId: string, key: string) => ["practice", "lookup", setId, key] as const,
};
export function isActiveRun(run: api.RunView | undefined | null) {
  return Boolean(run && ["pending", "processing", "cancel_requested"].includes(run.status));
}
export function practiceListOptions(page = 1) {
  return queryOptions({
    queryKey: practiceKeys.list(page),
    queryFn: () => api.listPracticeSets(page),
    staleTime: 0,
  });
}
export function practiceSetOptions(id: string) {
  return queryOptions({
    queryKey: practiceKeys.set(id),
    queryFn: () => api.getPracticeSet(id),
    enabled: Boolean(id),
    staleTime: 0,
  });
}
export function practicePlanOptions(id: string, version: number) {
  return queryOptions({
    queryKey: practiceKeys.plan(id, version),
    queryFn: () => api.getPracticePlan(id, version),
    enabled: Boolean(id && version),
    staleTime: 0,
  });
}
export function practiceRevisionOptions(id: string, revision: string) {
  return queryOptions({
    queryKey: practiceKeys.revision(id, revision),
    queryFn: () => api.getPracticeRevision(id, revision),
    enabled: Boolean(id && revision),
    staleTime: 0,
  });
}
export function practiceAttemptOptions(id: string) {
  return queryOptions({
    queryKey: practiceKeys.attempt(id),
    queryFn: () => api.getPracticeAttempt(id),
    enabled: Boolean(id),
    staleTime: 0,
    refetchInterval: (query) =>
      query.state.data?.submissions.some((s) => isActiveRun(s.run)) ? 2000 : false,
  });
}
export function practiceReportOptions(id: string) {
  return queryOptions({
    queryKey: practiceKeys.report(id),
    queryFn: () => api.getPracticeReport(id),
    enabled: Boolean(id),
    staleTime: 0,
    refetchInterval: (query) =>
      query.state.data?.questions.some((q) => isActiveRun(q.submission?.run)) ? 2000 : false,
  });
}
export function practiceGradeOptions(id: string, version: number) {
  return queryOptions({
    queryKey: practiceKeys.grade(id, version),
    queryFn: () => api.getPracticeGrade(id, version),
    enabled: Boolean(id && version),
    staleTime: 0,
  });
}
export function practiceRunOptions(id: string) {
  return queryOptions({
    queryKey: practiceKeys.run(id),
    queryFn: () => api.getPracticeRun(id),
    enabled: Boolean(id),
    staleTime: 0,
    refetchInterval: (query) => (isActiveRun(query.state.data) ? 2000 : false),
  });
}
export function practiceLookupOptions(setId: string, key: string, enabled = true) {
  return queryOptions({
    queryKey: practiceKeys.lookup(setId, key),
    queryFn: () => api.lookupPracticeRun(key, setId),
    enabled: Boolean(setId && key && enabled),
    retry: false,
    staleTime: 0,
    refetchInterval: (query) => (isActiveRun(query.state.data) ? 2000 : false),
  });
}
const localMeta = { errorMode: "local" as const, successToast: false };
function mutation<Input, Output>(name: string, fn: (input: Input) => Promise<Output>) {
  return mutationOptions({
    mutationKey: [...practiceKeys.all, name],
    mutationFn: (input: Input) => fn(input),
    meta: localMeta,
    retry: false,
  });
}
export function createPracticeOptions() {
  return mutation("create", api.createPracticeSet);
}
export function patchPracticeOptions() {
  return mutation("patch", ({ id, body }: { id: string; body: api.SetPatch }) =>
    api.patchPracticeSet(id, body),
  );
}
export function deletePracticeOptions(client: QueryClient) {
  return mutationOptions({
    ...mutation("delete", ({ id, version }: { id: string; version: number }) =>
      api.deletePracticeSet(id, version),
    ),
    onSuccess: async (_result, input) => {
      client.removeQueries({ queryKey: practiceKeys.set(input.id) });
      await client.invalidateQueries({ queryKey: practiceKeys.lists() });
    },
  });
}
export function planPracticeOptions() {
  return mutation("plan", ({ id, body }: { id: string; body: api.PlanRequest }) =>
    api.requestPracticePlan(id, body),
  );
}
export function generatePracticeOptions() {
  return mutation("generate", ({ id, body }: { id: string; body: api.GenerateRequest }) =>
    api.generatePractice(id, body),
  );
}
export function regeneratePracticeOptions() {
  return mutation("regenerate", ({ id, body }: { id: string; body: api.RegenerateRequest }) =>
    api.regeneratePractice(id, body),
  );
}
export function editQuestionOptions() {
  return mutation(
    "question-edit",
    ({ id, questionId, body }: { id: string; questionId: string; body: api.QuestionEdit }) =>
      api.editPracticeQuestion(id, questionId, body),
  );
}
export function deleteQuestionOptions() {
  return mutation(
    "question-delete",
    ({ id, questionId, version }: { id: string; questionId: string; version: number }) =>
      api.deletePracticeQuestion(id, questionId, version),
  );
}
export function startAttemptOptions() {
  return mutation("start", ({ id, body }: { id: string; body: api.AttemptCreate }) =>
    api.startPracticeAttempt(id, body),
  );
}
export function saveAnswerOptions() {
  return mutation(
    "save-answer",
    ({ id, questionId, body }: { id: string; questionId: string; body: api.AnswerSave }) =>
      api.savePracticeAnswer(id, questionId, body),
  );
}
export function submitAnswerOptions() {
  return mutation(
    "submit",
    ({ id, questionId, body }: { id: string; questionId: string; body: api.SubmitRequest }) =>
      api.submitPracticeAnswer(id, questionId, body),
  );
}
export function regradeOptions() {
  return mutation("regrade", ({ id, body }: { id: string; body: api.RegradeRequest }) =>
    api.regradePractice(id, body),
  );
}
export function completePracticeOptions() {
  return mutation("complete", ({ id, version }: { id: string; version: number }) =>
    api.completePractice(id, version),
  );
}
export function cancelRunOptions() {
  return mutation("cancel", api.cancelPracticeRun);
}
export function retryRunOptions() {
  return mutation("retry", ({ id, body }: { id: string; body: api.RetryRequest }) =>
    api.retryPracticeRun(id, body),
  );
}
export function practiceFeedbackOptions() {
  return mutation("feedback", api.setPracticeFeedback);
}

export function practiceSourceOptions(
  setId: string,
  revisionId: string,
  questionId: string,
  sourceId: string,
) {
  return queryOptions({
    queryKey: [...practiceKeys.revision(setId, revisionId), "source", questionId, sourceId],
    queryFn: () => api.getPracticeSource(setId, revisionId, questionId, sourceId),
    enabled: Boolean(setId && revisionId && questionId && sourceId),
    staleTime: 0,
  });
}
