import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import * as api from "./api";
import type { UserCaseDetail } from "./api";
import { QualityFeedbackDialog } from "./feedback-dialog";
import { MyQualityCasePage, MyQualityCasesPage } from "./user-pages";
vi.mock("@/features/auth/auth-provider", () => ({
  useAuth: () => ({ status: "authenticated", user: auth.user }),
  authenticatedAccessToken: vi.fn(),
}));
vi.mock("@/features/file-management/content-shell", () => ({
  ContentShell: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  createCase: vi.fn(),
  getCase: vi.fn(),
  listCases: vi.fn(),
  addMessage: vi.fn(),
  decideGrant: vi.fn(),
  revokeGrant: vi.fn(),
  closeCase: vi.fn(),
  withdrawCase: vi.fn(),
}));
const auth = vi.hoisted(() => ({
  user: { id: "owner", username: "learner", nickname: "学习者", role: "user", status: "active" },
}));
const detail: UserCaseDetail = {
  id: "case",
  case_number: "Q-2026-1",
  user_id: "owner",
  source_type: "learning_turn",
  source_id: "turn",
  trace_id: "trace",
  category: "wrong_answer",
  status: "waiting_user",
  version: 3,
  strategy_version: "fts-v1",
  assignee_id: "admin",
  created_at: "2026-10-03T00:00:00Z",
  updated_at: "2026-10-03T00:00:00Z",
  resolved_at: null,
  closed_at: null,
  resolution_code: null,
  resolution_summary: null,
  description: "私有描述",
  expected_result: "正确说明",
  grants: [
    {
      id: "grant",
      version: 2,
      status: "active",
      fields: ["query", "final_output"],
      chunk_ids: [],
      reason: "诊断本次回答",
      requester_id: null,
      expires_at: "2026-11-03T00:00:00Z",
      confirmed_at: "2026-10-03T00:00:00Z",
      revoked_at: null,
    },
  ],
  events: [
    {
      id: "public",
      action: "admin_message",
      actor_id: "admin",
      visibility: "user",
      version: 2,
      content: "公开说明",
      created_at: "2026-10-03T00:00:00Z",
    },
    {
      id: "internal",
      action: "admin_message",
      actor_id: "admin",
      visibility: "admin",
      version: 3,
      content: "不得展示的内部记录",
      created_at: "2026-10-03T00:00:00Z",
    },
  ],
};
let client: QueryClient;
beforeEach(() => {
  vi.clearAllMocks();
  auth.user.role = "user";
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  vi.mocked(api.getCase).mockResolvedValue(detail);
  vi.mocked(api.createCase).mockResolvedValue({ data: detail, message: "ok" });
  vi.mocked(api.listCases).mockResolvedValue({
    data: [detail],
    meta: { page: 1, page_size: 20, total: 1, total_pages: 1 },
  });
});
afterEach(() => {
  cleanup();
  client.clear();
});
function show(node: React.ReactNode) {
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}
function fill() {
  fireEvent.click(screen.getByLabelText("回答错误"));
  fireEvent.change(screen.getByLabelText("问题描述 *"), { target: { value: "回答与资料冲突" } });
}
it("反馈初始未同意，明确同意后只提交绑定turn/trace和本次范围", async () => {
  const created = vi.fn();
  show(
    <QualityFeedbackDialog
      open
      onOpenChange={vi.fn()}
      sourceId="turn"
      traceId="trace"
      onCreated={created}
    />,
  );
  const checkbox = screen.getByRole("checkbox");
  expect(checkbox).not.toBeChecked();
  fill();
  expect(screen.getByRole("button", { name: "提交反馈" })).toBeDisabled();
  fireEvent.click(checkbox);
  fireEvent.click(screen.getByRole("button", { name: "提交反馈" }));
  await waitFor(() => expect(created).toHaveBeenCalledWith("case"));
  expect(api.createCase).toHaveBeenCalledWith(
    expect.objectContaining({
      source_type: "learning_turn",
      source_id: "turn",
      trace_id: "trace",
      description: "回答与资料冲突",
      basic_access_confirmed: true,
      request_key: expect.any(String),
    }),
    expect.anything(),
  );
});
it("关闭弹窗后迟到创建成功不执行旧页面跳转", async () => {
  let complete!: (value: Awaited<ReturnType<typeof api.createCase>>) => void;
  vi.mocked(api.createCase).mockReturnValue(
    new Promise((resolve) => {
      complete = resolve;
    }),
  );
  const created = vi.fn();
  const view = show(
    <QualityFeedbackDialog
      open
      onOpenChange={vi.fn()}
      sourceId="turn"
      traceId="trace"
      onCreated={created}
    />,
  );
  fill();
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "提交反馈" }));
  await waitFor(() => expect(api.createCase).toHaveBeenCalled());
  view.unmount();
  complete({ data: detail, message: "ok" });
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(created).not.toHaveBeenCalled();
});
it("本人详情只展示public事件并按真实版本提交补充", async () => {
  vi.mocked(api.addMessage).mockResolvedValue({
    data: { ...detail, version: 4, status: "triaging" },
    message: "ok",
  });
  show(<MyQualityCasePage id="case" />);
  await screen.findByText("私有描述");
  expect(screen.getByText("公开说明")).toBeInTheDocument();
  expect(screen.queryByText("不得展示的内部记录")).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole("textbox", { name: "补充说明" }), {
    target: { value: "复现步骤" },
  });
  fireEvent.click(screen.getByRole("button", { name: "提交补充" }));
  await waitFor(() =>
    expect(api.addMessage).toHaveBeenCalledWith("case", {
      expected_version: 3,
      content: "复现步骤",
    }),
  );
});
it("追加grant没有自动同意，明确拒绝带上case和grant版本", async () => {
  const request = {
    ...detail.grants[0],
    id: "extra",
    status: "pending" as const,
    version: 5,
    fields: ["candidate_excerpts" as const],
    chunk_ids: ["chunk"],
    reason: "比较指定候选",
  };
  vi.mocked(api.getCase).mockResolvedValue({ ...detail, grants: [...detail.grants, request] });
  vi.mocked(api.decideGrant).mockResolvedValue({ data: { ...detail, version: 4 }, message: "ok" });
  show(<MyQualityCasePage id="case" />);
  await screen.findByText("比较指定候选");
  expect(api.decideGrant).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "拒绝" }));
  await waitFor(() =>
    expect(api.decideGrant).toHaveBeenCalledWith("case", "extra", {
      expected_version: 3,
      expected_grant_version: 5,
      approved: false,
    }),
  );
});
it("跨owner异常响应不展示正文，管理员账号不发本人查询", async () => {
  vi.mocked(api.getCase).mockResolvedValue({ ...detail, user_id: "other" });
  const view = show(<MyQualityCasePage id="case" />);
  await screen.findByText("这条反馈不可访问。");
  expect(screen.queryByText("私有描述")).not.toBeInTheDocument();
  view.unmount();
  vi.mocked(api.getCase).mockClear();
  auth.user.role = "admin";
  show(<MyQualityCasePage id="case" />);
  expect(api.getCase).not.toHaveBeenCalled();
});
it("列表使用真实分页和status，页内筛选不冒充全局搜索", async () => {
  show(<MyQualityCasesPage />);
  await screen.findByText("Q-2026-1");
  expect(api.listCases).toHaveBeenCalledWith({ page: 1, page_size: 20 }, expect.any(AbortSignal));
  fireEvent.change(screen.getByRole("textbox", { name: "筛选本页工单号" }), {
    target: { value: "missing" },
  });
  expect(screen.queryByText("Q-2026-1")).not.toBeInTheDocument();
  expect(screen.getByText("暂无符合条件的反馈")).toBeInTheDocument();
});

it("本人撤销后接口仍含自己的陈述时，本页清正文但不自动重取循环", async () => {
  vi.mocked(api.getCase).mockResolvedValue({
    ...detail,
    grants: [{ ...detail.grants[0], status: "revoked" }],
  });
  show(<MyQualityCasePage id="case" />);
  await screen.findByText("正文授权已结束，本页不再显示问题描述。");
  await screen.findByText("已撤销");
  expect(screen.queryByText("私有描述")).not.toBeInTheDocument();
  expect(screen.queryByText("公开说明")).not.toBeInTheDocument();
  expect(api.getCase).toHaveBeenCalledTimes(1);
});
