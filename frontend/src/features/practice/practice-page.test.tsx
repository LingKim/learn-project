import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { PracticePage } from "./practice-page";
import * as api from "./api";
import { emptyAttempt, pendingRun, singleQuestion } from "./fixtures.test-support";
import { practiceKeys } from "./queries";
const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
const authentication = vi.hoisted(() => ({ user: { id: "owner-id", username: "owner" } }));
const profiles = vi.hoisted(() => ({ read: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/features/auth/auth-provider", () => ({ useAuth: () => authentication }));
vi.mock("@/features/file-management/content-shell", () => ({
  ContentShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock("@/features/user-profile/queries", () => ({
  userProfileQueryOptions: () => ({
    queryKey: ["profile"],
    queryFn: () => profiles.read(),
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
  vi.resetAllMocks();
  authentication.user = { id: "owner-id", username: "owner" };
  profiles.read.mockResolvedValue({
    username: "owner",
    target_job: null,
    target_skills: [],
    preferred_language: "zh-CN",
  });
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
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}
function mount(props: React.ComponentProps<typeof PracticePage>) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  client.setQueryData(["profile"], { username: "owner" });
  render(
    <QueryClientProvider client={client}>
      <PracticePage {...props} />
    </QueryClientProvider>,
  );
}
describe("配置确认与异步恢复", () => {
  it("本页remember更新request参数后仍接纳正常响应并结束posting恢复lookup", async () => {
    const request = deferred<Awaited<ReturnType<typeof api.generatePractice>>>();
    vi.mocked(api.generatePractice).mockReturnValue(request.promise);
    vi.mocked(api.getPracticeRun).mockResolvedValue({
      ...pendingRun,
      status: "succeeded",
      result_ref: { type: "plan", id: "plan", version: 3 },
    });
    vi.mocked(api.lookupPracticeRun).mockResolvedValue({ ...pendingRun, id: "normal-run" });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const view = render(
      <QueryClientProvider client={client}>
        <PracticePage setId="set" runId="run" />
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "使用原配置生成" }));
    await waitFor(() => expect(api.generatePractice).toHaveBeenCalled());
    const requestKey = vi.mocked(api.generatePractice).mock.calls[0][1].request_key;
    expect(router.replace).toHaveBeenCalledWith(`/learning/practice/set?request=${requestKey}`, {
      scroll: false,
    });
    view.rerender(
      <QueryClientProvider client={client}>
        <PracticePage setId="set" requestKey={requestKey} />
      </QueryClientProvider>,
    );
    await act(async () => {
      request.resolve({
        data: { ...pendingRun, id: "normal-run", request_key: requestKey },
        message: "ok",
      });
    });
    expect(client.getQueryData(practiceKeys.run("normal-run"))).toBeDefined();
    expect(router.replace).toHaveBeenCalledWith("/learning/practice/set?run=normal-run", {
      scroll: false,
    });
    await waitFor(() => expect(api.lookupPracticeRun).toHaveBeenCalledWith(requestKey, "set"));
  });
  it("画像首次慢回不重挂新练习表单或丢失已经编辑的配置", async () => {
    const profile = deferred<{
      username: string;
      target_job: null;
      target_skills: string[];
      preferred_language: string;
    }>();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    profiles.read.mockReturnValue(profile.promise);
    const view = render(
      <QueryClientProvider client={client}>
        <PracticePage initialConfig={config} />
      </QueryClientProvider>,
    );
    fireEvent.change(screen.getByLabelText("知识点"), { target: { value: "已输入的知识点" } });
    await act(async () => {
      profile.resolve({
        username: "owner",
        target_job: null,
        target_skills: [],
        preferred_language: "zh-CN",
      });
    });
    expect(screen.getByLabelText("知识点")).toHaveValue("已输入的知识点");
    view.unmount();
  });
  it("新建配置响应晚于离开页面时不再创建方案或跳回旧题集", async () => {
    const created = deferred<Awaited<ReturnType<typeof api.createPracticeSet>>>();
    vi.mocked(api.createPracticeSet).mockReturnValue(created.promise);
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const view = render(
      <QueryClientProvider client={client}>
        <PracticePage initialConfig={config} initialTitle="新建合成题集" />
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "生成题目方案" }));
    await waitFor(() => expect(api.createPracticeSet).toHaveBeenCalled());
    view.unmount();
    await act(async () => {
      created.resolve({ data: set, message: "ok" });
    });
    expect(api.requestPracticePlan).not.toHaveBeenCalled();
    expect(router.push).not.toHaveBeenCalled();
  });
  it("开始练习响应晚于离开页面时不能跳回旧attempt", async () => {
    const started = deferred<Awaited<ReturnType<typeof api.startPracticeAttempt>>>();
    vi.mocked(api.startPracticeAttempt).mockReturnValue(started.promise);
    vi.mocked(api.getPracticeSet).mockResolvedValue({
      ...set,
      revision,
      current_revision_id: revision.id,
    });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const view = render(
      <QueryClientProvider client={client}>
        <PracticePage setId="set" />
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "开始练习" }));
    await waitFor(() => expect(api.startPracticeAttempt).toHaveBeenCalled());
    view.unmount();
    await act(async () => {
      started.resolve({ data: emptyAttempt, message: "ok" });
    });
    expect(router.push).not.toHaveBeenCalled();
  });
  it.each(["attempt", "report", "unmount"])(
    "离开%s上下文后取消任务的迟到结果不能改缓存或地址",
    async (change) => {
      const cancellation = deferred<Awaited<ReturnType<typeof api.cancelPracticeRun>>>();
      vi.mocked(api.cancelPracticeRun).mockReturnValue(cancellation.promise);
      vi.mocked(api.getPracticeRun).mockResolvedValue(pendingRun);
      vi.mocked(api.getPracticeAttempt).mockResolvedValue(emptyAttempt);
      vi.mocked(api.getPracticeReport).mockResolvedValue({
        attempt_id: "attempt",
        total_questions: 1,
        submitted_count: 0,
        graded_count: 0,
        status: "completed",
        source_mode: "general",
        score: null,
        max_score: null,
        questions: [],
        topics: [],
      });
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      client.setQueryData(["profile"], { username: "owner" });
      const view = render(
        <QueryClientProvider client={client}>
          <PracticePage setId="set" attemptId="attempt" runId="run" />
        </QueryClientProvider>,
      );
      fireEvent.click(await screen.findByRole("button", { name: "取消任务" }));
      await waitFor(() => expect(api.cancelPracticeRun).toHaveBeenCalled());
      if (change === "unmount") view.unmount();
      else
        view.rerender(
          <QueryClientProvider client={client}>
            <PracticePage
              setId="set"
              attemptId={change === "attempt" ? "another-attempt" : "attempt"}
              report={change === "report"}
              runId="run"
            />
          </QueryClientProvider>,
        );
      router.replace.mockClear();
      await act(async () => {
        cancellation.resolve({ data: { ...pendingRun, status: "cancelled" }, message: "ok" });
      });
      expect(router.replace).not.toHaveBeenCalled();
      expect(client.getQueryData<api.RunView>(practiceKeys.run("run"))?.status).toBe("pending");
    },
  );
  it("跨题集迟到失败不得lookup旧请求、显示旧错误或结束新请求的busy状态", async () => {
    const oldRequest = deferred<Awaited<ReturnType<typeof api.generatePractice>>>();
    const newRequest = deferred<Awaited<ReturnType<typeof api.generatePractice>>>();
    vi.mocked(api.generatePractice)
      .mockReturnValueOnce(oldRequest.promise)
      .mockReturnValueOnce(newRequest.promise);
    vi.mocked(api.lookupPracticeRun).mockRejectedValue(
      new ApiError("旧请求不存在", { status: 404 }),
    );
    vi.mocked(api.getPracticeRun).mockResolvedValue({
      ...pendingRun,
      status: "succeeded",
      result_ref: { type: "plan", id: "plan", version: 3 },
    });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    client.setQueryData(["profile"], { username: "owner" });
    client.setQueryData(["profile"], { username: "owner" });
    const view = render(
      <QueryClientProvider client={client}>
        <PracticePage setId="set" runId="run" />
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "使用原配置生成" }));
    await waitFor(() => expect(api.generatePractice).toHaveBeenCalledTimes(1));
    view.rerender(
      <QueryClientProvider client={client}>
        <PracticePage setId="another-set" runId="run" />
      </QueryClientProvider>,
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "使用原配置生成" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "使用原配置生成" }));
    await waitFor(() => expect(api.generatePractice).toHaveBeenCalledTimes(2));
    await act(async () => {
      oldRequest.reject(new ApiError("旧请求网络失败", { errorKey: "NETWORK_ERROR" }));
    });
    expect(api.lookupPracticeRun).not.toHaveBeenCalled();
    expect(screen.queryByText("旧请求网络失败")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("知识点")).not.toBeInTheDocument();
    await act(async () => {
      newRequest.resolve({ data: { ...pendingRun, id: "new-run" }, message: "ok" });
    });
  });
  it("组件卸载后生成响应不能写run缓存或跳回旧页面", async () => {
    const request = deferred<Awaited<ReturnType<typeof api.generatePractice>>>();
    vi.mocked(api.generatePractice).mockReturnValue(request.promise);
    vi.mocked(api.getPracticeRun).mockResolvedValue({
      ...pendingRun,
      status: "succeeded",
      result_ref: { type: "plan", id: "plan", version: 3 },
    });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    client.setQueryData(["profile"], { username: "owner" });
    client.setQueryData(["profile"], { username: "owner" });
    const view = render(
      <QueryClientProvider client={client}>
        <PracticePage setId="set" runId="run" />
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "使用原配置生成" }));
    await waitFor(() => expect(api.generatePractice).toHaveBeenCalled());
    view.unmount();
    router.replace.mockClear();
    await act(async () => {
      request.resolve({ data: { ...pendingRun, id: "late-run" }, message: "ok" });
    });
    expect(router.replace).not.toHaveBeenCalled();
    expect(client.getQueryData(practiceKeys.run("late-run"))).toBeUndefined();
  });
  it("同一组件切换题集和URL任务后只读取新题集的run", async () => {
    vi.mocked(api.getPracticeRun).mockImplementation(async (id) => ({ ...pendingRun, id }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(["profile"], { username: "owner" });
    const view = render(
      <QueryClientProvider client={client}>
        <PracticePage setId="set" runId="first-run" />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(api.getPracticeRun).toHaveBeenCalledWith("first-run"));
    view.rerender(
      <QueryClientProvider client={client}>
        <PracticePage setId="other-set" runId="second-run" />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(api.getPracticeRun).toHaveBeenCalledWith("second-run"));
  });
  it("切换账号后不继续用前一个账号的session恢复指针", async () => {
    sessionStorage.setItem(
      "practice-request:v1:owner:set",
      JSON.stringify({
        version: 1,
        requestKey: "owner-request",
        operation: "plan",
        targetId: "set",
        runId: "owner-run",
      }),
    );
    vi.mocked(api.getPracticeRun).mockResolvedValue(pendingRun);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(
      <QueryClientProvider client={client}>
        <PracticePage setId="set" />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(api.getPracticeRun).toHaveBeenCalledWith("owner-run"));
    authentication.user = { id: "other-id", username: "other-owner" };
    view.rerender(
      <QueryClientProvider client={client}>
        <PracticePage setId="set" />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText("等待处理")).not.toBeInTheDocument());
    expect(api.lookupPracticeRun).not.toHaveBeenCalledWith("owner-request", "set");
  });
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
