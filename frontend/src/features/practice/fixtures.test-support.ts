import type { AttemptView, PracticeQuestion, RunView } from "./api";
export const baseQuestion = {
  question_id: "11111111-1111-4111-8111-111111111111",
  difficulty: "medium" as const,
  topics: ["事务"],
  stem: "合成事务知识问题",
  answer_explanation: "合成答案讲解",
  rubric: [{ id: "understanding", description: "解释事务边界", max_score: 1 }],
  source_refs: [],
};
export const singleQuestion = {
  ...baseQuestion,
  type: "single_choice",
  options: [
    { id: "A", text: "加入事务" },
    { id: "B", text: "独立事务" },
  ],
  answer: "B",
} satisfies PracticeQuestion;
export const textQuestion = {
  ...baseQuestion,
  type: "short_answer",
  answer: ["事务边界"],
} satisfies PracticeQuestion;
export const emptyAttempt: AttemptView = {
  id: "attempt",
  set_id: "set",
  revision_id: "revision",
  status: "active",
  version: 1,
  current_question_id: baseQuestion.question_id,
  questions: [textQuestion],
  answers: [],
  submissions: [],
  source_available: true,
  question_feedback: {},
  started_at: "2026-10-03T00:00:00Z",
  completed_at: null,
};
export const pendingRun: RunView = {
  id: "run",
  operation: "plan",
  status: "pending",
  stage: "pending",
  attempt_count: 1,
  retryable: false,
  error_key: null,
  submission_id: null,
  result_ref: null,
  request_key: "key",
  input_digest: "a".repeat(64),
};
