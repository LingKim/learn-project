import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { PracticePage } from "./practice-page";
import * as api from "./api";
import { pendingRun, singleQuestion } from "./fixtures.test-support";
const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/features/file-management/content-shell", () => ({
  ContentShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock("@/features/user-profile/queries", () => ({
  userProfileQueryOptions: () => ({
    queryKey: ["profile"],
    queryFn: async () => ({
      username: "owner",
      target_job: null,
      target_skills: [],
      preferred_language: "zh-CN",
    }),
  }),
}));
vi.mock("@/features/file-management/queries", () => ({
  knowledgeBaseListQueryOptions: () => ({
    queryKey: ["bases"],
    queryFn: async () => ({ data: [] }),
  }),
  knowledgeFileListQueryOptions: () => ({
    queryKey: ["files"],
    queryFn: async () => ({ data: [] }),
  }),
}));
vi.mock("./api", () => ({
  listPracticeSets: vi.fn(),
  getPracticeSet: vi.fn(),
  getPracticePlan: vi.fn(),
  getPracticeRevision: vi.fn(),
  getPracticeAttempt: vi.fn(),
  getPracticeReport: vi.fn(),
  getPracticeGrade: vi.fn(),
  getPracticeRun: vi.fn(),
  lookupPracticeRun: vi.fn(),
  createPracticeSet: vi.fn(),
  patchPracticeSet: vi.fn(),
  requestPracticePlan: vi.fn(),
  generatePractice: vi.fn(),
  regeneratePractice: vi.fn(),
  editPracticeQuestion: vi.fn(),
  deletePracticeQuestion: vi.fn(),
  startPracticeAttempt: vi.fn(),
  regradePractice: vi.fn(),
  deletePracticeSet: vi.fn(),
  cancelPracticeRun: vi.fn(),
  retryPracticeRun: vi.fn(),
  setPracticeFeedback: vi.fn(),
  getPracticeSource: vi.fn(),
}));
const config: api.PracticeConfig = {
  mode: "practice",
  source_mode: "general",
  topic: "事务",
  question_count: 1,
  question_types: { single_choice: 1 },
  difficulty: "medium",
};
const set: api.SetDetail = {
  id: "set",
  title: "合成练习",
  config,
  version: 4,
  current_revision_id: null,
  source_available: true,
  created_at: "2026-10-03T00:00:00Z",
  updated_at: "2026-10-03T00:00:00Z",
  revision: null,
  attempts: [],
};
const plan: api.PlanView = {
  id: "plan",
  set_id: "set",
  version: 3,
  base_set_version: 4,
  suggestions: ["合成建议"],
  original: {
    config,
    summary: "原始合成配置",
    config_digest: "a".repeat(64),
    effective_context: {},
  },
  recommended: {
    config,
    summary: "推荐合成配置",
    config_digest: "b".repeat(64),
    effective_context: {},
  },
};
const revision: api.RevisionView = {
  id: "original-revision",
  set_id: "set",
  version: 2,
  config,
  effective_context: {},
  questions: [singleQuestion],
  source_available: true,
  source_mode: "general",
  reason: "generate",
  question_feedback: {},
  created_at: "2026-10-03T00:00:00Z",
};
beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  vi.mocked(api.listPracticeSets).mockResolvedValue({
    data: [],
    meta: { page: 1, page_size: 20, total: 0, total_pages: 0 },
  });
  vi.mocked(api.getPracticeSet).mockResolvedValue(set);
  vi.mocked(api.getPracticePlan).mockResolvedValue(plan);
  vi.mocked(api.getPracticeRevision).mockResolvedValue(revision);
  vi.mocked(api.generatePractice).mockResolvedValue({
    data: { ...pendingRun, id: "generate-run", operation: "generate" },
    message: "ok",
  });
});
afterEach(cleanup);
function mount(props: React.ComponentProps<typeof PracticePage>) {
  render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
        })
      }
    >
      <PracticePage {...props} />
    </QueryClientProvider>,
  );
}
describe("配置确认与异步恢复", () => {
  it("展示不可变方案后按所选候选摘要确认，未确认前不生成", async () => {
    vi.mocked(api.getPracticeRun).mockResolvedValue({
      ...pendingRun,
      status: "succeeded",
      result_ref: { type: "plan", id: "plan", version: 3 },
    });
    mount({ setId: "set", runId: "run" });
    await screen.findByText("推荐合成配置");
    expect(api.generatePractice).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "采用推荐配置生成" }));
    await waitFor(() =>
      expect(api.generatePractice).toHaveBeenCalledWith(
        "set",
        expect.objectContaining({
          expected_version: 4,
          plan_version: 3,
          candidate: "recommended",
          confirmed_config_digest: "b".repeat(64),
        }),
      ),
    );
  });
  it("响应丢失只按request_key读取后台任务，不自动重发模型", async () => {
    vi.mocked(api.getPracticeRun).mockResolvedValue({
      ...pendingRun,
      status: "succeeded",
      result_ref: { type: "plan", id: "plan", version: 3 },
    });
    vi.mocked(api.generatePractice).mockRejectedValue(
      new ApiError("网络失败", { errorKey: "NETWORK_ERROR" }),
    );
    vi.mocked(api.lookupPracticeRun).mockResolvedValue({
      ...pendingRun,
      id: "actual-run",
      operation: "generate",
      status: "processing",
      stage: "generate",
    });
    mount({ setId: "set", runId: "run" });
    fireEvent.click(await screen.findByRole("button", { name: "使用原配置生成" }));
    await waitFor(() => expect(api.lookupPracticeRun).toHaveBeenCalled());
    expect(api.generatePractice).toHaveBeenCalledTimes(1);
    await screen.findByText("生成题目");
  });
  it("刷新用恢复key读取当前任务，GET不触发新的方案或生成", async () => {
    vi.mocked(api.lookupPracticeRun).mockResolvedValue({ ...pendingRun, status: "processing" });
    mount({ setId: "set", requestKey: "saved-key" });
    await screen.findByText("等待处理");
    expect(api.lookupPracticeRun).toHaveBeenCalledWith("saved-key", "set");
    expect(api.requestPracticePlan).not.toHaveBeenCalled();
    expect(api.generatePractice).not.toHaveBeenCalled();
  });
  it("按run的指定revision读结果，不误显示已经更新的当前指针", async () => {
    vi.mocked(api.getPracticeSet).mockResolvedValue({
      ...set,
      current_revision_id: "other-revision",
      revision: {
        ...revision,
        id: "other-revision",
        questions: [{ ...singleQuestion, stem: "另一次后来的题目" }],
      },
    });
    vi.mocked(api.getPracticeRun).mockResolvedValue({
      ...pendingRun,
      status: "succeeded",
      operation: "generate",
      result_ref: { type: "revision", id: "original-revision", version: 2 },
    });
    mount({ setId: "set", runId: "run" });
    await screen.findAllByText("合成事务知识问题");
    expect(api.getPracticeRevision).toHaveBeenCalledWith("set", "original-revision");
    expect(screen.queryByText("另一次后来的题目")).not.toBeInTheDocument();
  });
});
