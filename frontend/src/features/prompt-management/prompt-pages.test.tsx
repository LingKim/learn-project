import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AdminRoute } from "@/features/auth/auth-route";
import { useAuth } from "@/features/auth/auth-provider";
import * as api from "./api";
import { definition, draft } from "./fixtures.test-support";
import { PromptDetailPage } from "./prompt-detail-page";
import { PromptListPage } from "./prompt-list-page";
import { promptManagementKeys } from "./queries";

const routing = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => routing }));
vi.mock("@/features/auth/auth-provider", () => ({ useAuth: vi.fn() }));
vi.mock("./api", () => ({
  listPromptDefinitions: vi.fn(),
  getPromptDefinition: vi.fn(),
  listPromptVersions: vi.fn(),
  getPromptVersion: vi.fn(),
  getPromptDiff: vi.fn(),
  listPromptAuditEvents: vi.fn(),
  createPromptDraft: vi.fn(),
  patchPromptDraft: vi.fn(),
  previewPromptVersion: vi.fn(),
  evaluatePromptVersion: vi.fn(),
  publishPromptVersion: vi.fn(),
  rollbackPromptDefinition: vi.fn(),
  setPromptDefinitionStatus: vi.fn(),
}));
let client: QueryClient;
const meta = { page: 1, page_size: 20, total: 1, total_pages: 1 };
beforeEach(() => {
  client = new QueryClient();
  vi.clearAllMocks();
  vi.mocked(api.listPromptDefinitions).mockResolvedValue({ data: [definition], meta });
  vi.mocked(api.getPromptDefinition).mockResolvedValue({
    ...definition,
    active_version_id: null,
    runtime_status: "disabled",
  });
  vi.mocked(api.listPromptVersions).mockResolvedValue({
    data: [draft, { ...draft, id: "historical", version: 1, status: "retired" }],
    meta,
  });
  vi.mocked(api.getPromptVersion).mockImplementation(async (id) =>
    id === "historical"
      ? { ...draft, id, version: 1, status: "retired", content: "合成历史正文" }
      : draft,
  );
  vi.mocked(api.listPromptAuditEvents).mockResolvedValue({
    data: [],
    meta: { ...meta, total: 0, total_pages: 0 },
  });
});
afterEach(() => {
  cleanup();
  client.clear();
});
function wrap(child: React.ReactNode) {
  return render(<QueryClientProvider client={client}>{child}</QueryClientProvider>);
}

it("普通用户访问实际Prompt页面时不挂载组件、不请求定义或正文", () => {
  vi.mocked(useAuth).mockReturnValue({
    status: "authenticated",
    user: {
      id: "synthetic-user",
      username: "synthetic",
      nickname: "合成用户",
      role: "user",
      status: "active",
    },
    completeAuthentication: vi.fn(),
    logout: vi.fn(),
  });
  wrap(
    <AdminRoute>
      <PromptListPage />
    </AdminRoute>,
  );
  expect(screen.getByText("无权访问管理功能")).toBeInTheDocument();
  expect(api.listPromptDefinitions).not.toHaveBeenCalled();
  expect(api.getPromptVersion).not.toHaveBeenCalled();
});

it("列表筛选实际注册Agent/场景，不提供创建空定义入口或自动调用模型", async () => {
  wrap(<PromptListPage />);
  await waitFor(() =>
    expect(screen.getByRole("link", { name: "练习题目生成" })).toBeInTheDocument(),
  );
  expect(screen.queryByRole("button", { name: "创建定义" })).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Agent"), { target: { value: "question_generator" } });
  fireEvent.change(screen.getByLabelText("场景"), { target: { value: "practice_generate" } });
  fireEvent.click(screen.getByRole("button", { name: "筛选" }));
  await waitFor(() =>
    expect(api.listPromptDefinitions).toHaveBeenCalledWith(
      expect.objectContaining({
        agent_key: "question_generator",
        scene_key: "practice_generate",
        page: 1,
      }),
      expect.any(AbortSignal),
    ),
  );
  expect(api.evaluatePromptVersion).not.toHaveBeenCalled();
});

it("切换版本前提示未保存草稿；确认后读取真正历史版本且旧正文回收", async () => {
  const view = wrap(<PromptDetailPage definitionId="definition" />);
  await screen.findByLabelText("Prompt 正文");
  fireEvent.change(screen.getByLabelText("Prompt 正文"), { target: { value: "未保存的合成编辑" } });
  fireEvent.click(screen.getByRole("button", { name: /v1/ }));
  expect(screen.getByRole("dialog")).toHaveTextContent("离开未保存的草稿");
  expect(api.getPromptVersion).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
  expect(screen.getByLabelText("Prompt 正文")).toHaveValue("未保存的合成编辑");
  fireEvent.click(screen.getByRole("button", { name: /v1/ }));
  fireEvent.click(screen.getByRole("button", { name: "放弃修改并继续" }));
  await waitFor(() => expect(screen.getByLabelText("Prompt 正文")).toHaveValue("合成历史正文"));
  expect(screen.getByLabelText("Prompt 正文")).toHaveAttribute("readonly");
  await waitFor(() =>
    expect(client.getQueryData(promptManagementKeys.detail("draft"))).toBeUndefined(),
  );
  view.unmount();
  await waitFor(() =>
    expect(client.getQueryData(promptManagementKeys.detail("historical"))).toBeUndefined(),
  );
});

it("未保存时阻止返回链接及硬离页，取消保留输入而不持久化正文", async () => {
  const storage = vi.spyOn(Storage.prototype, "setItem");
  wrap(<PromptDetailPage definitionId="definition" />);
  await screen.findByLabelText("Prompt 正文");
  fireEvent.change(screen.getByLabelText("Prompt 正文"), { target: { value: "临时合成内容" } });
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  expect(event.defaultPrevented).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "← 提示词模板列表" }));
  expect(routing.push).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
  expect(screen.getByLabelText("Prompt 正文")).toHaveValue("临时合成内容");
  expect(storage).not.toHaveBeenCalled();
});
