import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { GradePanel, FeedbackButtons } from "./grade-panel";
import { ReportPanel } from "./report-panel";
import { SourceLinks } from "./source-links";
import { RunStatus } from "./run-status";
import { practiceSourceOptions } from "./queries";
import * as api from "./api";
import { baseQuestion, emptyAttempt, pendingRun, singleQuestion } from "./fixtures.test-support";
vi.mock("./api", () => ({
  setPracticeFeedback: vi.fn(),
  getPracticeSource: vi.fn(),
  cancelPracticeRun: vi.fn(),
  retryPracticeRun: vi.fn(),
}));
const grade: api.GradeView = {
  id: "grade",
  submission_id: "sub",
  version: 2,
  level: "partial",
  dimensions: [
    {
      dimension_id: "understanding",
      level: "partial",
      evidence: [{ quote: "独立事务", start: 0, end: 4 }],
    },
  ],
  confidence: 0.6,
  low_confidence: true,
  rubric: baseQuestion.rubric,
  topics: ["事务"],
  source_mode: "general",
  created_at: "2026-10-03T00:00:00Z",
  feedback: null,
  error_reasons: ["缺少回滚条件"],
  suggestions: ["补充异常传播"],
};
function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
        })
      }
    >
      {children}
    </QueryClientProvider>
  );
}
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
it("低置信度点评含回答证据、规则、建议，不虚构分数或代码执行结果", () => {
  render(<GradePanel grade={grade} subjective code onRegrade={vi.fn()} />, { wrapper });
  expect(screen.getByText(/低置信度/)).toBeInTheDocument();
  expect(screen.getByText(/位置 0–4/)).toBeInTheDocument();
  expect(screen.getByText("补充异常传播")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "重新评分" })).toBeInTheDocument();
  expect(screen.queryByText(/已编译|测试通过|总分/)).not.toBeInTheDocument();
});
it("读取新持久反馈后同步选择态，取消选择发送null", async () => {
  vi.mocked(api.setPracticeFeedback).mockResolvedValue({
    data: { id: "feedback", grade_id: "grade", feedback: null },
    message: "ok",
  });
  const view = render(<FeedbackButtons target={{ grade_id: "grade" }} value={null} />, { wrapper });
  view.rerender(<FeedbackButtons target={{ grade_id: "grade" }} value="helpful" />);
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "有帮助" })).toHaveAttribute("aria-pressed", "true"),
  );
  fireEvent.click(screen.getByRole("button", { name: "有帮助" }));
  await waitFor(() =>
    expect(api.setPracticeFeedback).toHaveBeenCalledWith({ grade_id: "grade", feedback: null }),
  );
});
it("未提交覆盖清楚列出，不显示总分或把未评分当零分", () => {
  const report: api.ReportView = {
    attempt_id: "attempt",
    status: "completed",
    total_questions: 1,
    submitted_count: 0,
    graded_count: 0,
    questions: [
      {
        question_id: baseQuestion.question_id,
        topics: ["事务"],
        submission: null,
        status: "unsubmitted",
      },
    ],
    topics: [{ topic: "事务", unsubmitted: 1, insufficient_sample: true }],
    source_mode: "general",
    score: null,
    max_score: null,
  };
  render(
    <ReportPanel
      report={report}
      attempt={emptyAttempt}
      busy={false}
      onRegrade={vi.fn()}
      onPracticeAgain={vi.fn()}
    />,
    { wrapper },
  );
  expect(screen.getByText("未满足汇总评分条件")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "合成事务知识问题" }));
  expect(screen.getByText(/不会把草稿当作已提交回答/)).toBeInTheDocument();
  expect(screen.getByText("样本不足，不推断长期掌握度。")).toBeInTheDocument();
});
it("失效历史引用禁用预览，没有原文请求", () => {
  const ref = {
    source_id: "source",
    file_id: "file",
    file_asset_id: "asset",
    processing_version_id: "processing",
    chunk_id: "chunk",
    display_name: "合成资料",
    page_start: 1,
  };
  render(
    <SourceLinks
      setId="set"
      revisionId="old-revision"
      question={{ ...singleQuestion, source_refs: [ref] }}
      available={false}
    />,
    { wrapper },
  );
  expect(screen.getByRole("button", { name: "来源已失效" })).toBeDisabled();
  expect(api.getPracticeSource).not.toHaveBeenCalled();
});
it("已打开资料被撤权后立即隐藏原文、关闭弹窗并清理缓存", async () => {
  const ref = {
    source_id: "source",
    file_id: "file",
    file_asset_id: "asset",
    processing_version_id: "processing",
    chunk_id: "chunk",
    display_name: "合成资料",
  };
  vi.mocked(api.getPracticeSource).mockResolvedValue({
    source: ref,
    available: true,
    evidence: "撤权前合成原文",
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const content = (available: boolean) => (
    <QueryClientProvider client={client}>
      <SourceLinks
        setId="set"
        revisionId="revision"
        question={{ ...singleQuestion, source_refs: [ref] }}
        available={available}
      />
    </QueryClientProvider>
  );
  const view = render(content(true));
  fireEvent.click(screen.getByRole("button", { name: "合成资料" }));
  await screen.findByText("撤权前合成原文");
  expect(
    client.getQueryData(
      practiceSourceOptions("set", "revision", singleQuestion.question_id, "source").queryKey,
    ),
  ).toBeDefined();
  view.rerender(content(false));
  expect(screen.queryByText("撤权前合成原文")).not.toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "来源已失效" })).toBeDisabled();
  expect(
    client.getQueryData(
      practiceSourceOptions("set", "revision", singleQuestion.question_id, "source").queryKey,
    ),
  ).toBeUndefined();
  expect(api.getPracticeSource).toHaveBeenCalledTimes(1);
});
it("取消或重试只有用户操作才调用API，保留当前request key/digest", async () => {
  vi.mocked(api.retryPracticeRun).mockResolvedValue({ data: pendingRun, message: "ok" });
  const change = vi.fn();
  render(
    <RunStatus
      run={{
        ...pendingRun,
        status: "failed",
        retryable: true,
        error_key: "PRACTICE_GENERATION_INVALID",
      }}
      onChange={change}
      onAdjust={vi.fn()}
    />,
    { wrapper },
  );
  expect(api.retryPracticeRun).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "重试任务" }));
  await waitFor(() =>
    expect(api.retryPracticeRun).toHaveBeenCalledWith("run", {
      request_key: pendingRun.request_key,
      input_digest: pendingRun.input_digest,
    }),
  );
  expect(change).toHaveBeenCalledWith(pendingRun);
});
