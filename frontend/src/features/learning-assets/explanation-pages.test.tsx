import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ExplanationPage } from "./explanation-page";
import { ExplanationDetailPage } from "./explanation-detail-page";
import { syntheticCard, syntheticWeakness } from "./fixtures.test-support";
import type { ExplanationDetail, KnowledgeRunView } from "./api";
import * as api from "./api";
import { ApiError } from "@/lib/api/errors";
import { readKnowledgeRequest, writeKnowledgeRequest } from "./request-recovery";

const navigation = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => navigation }));
vi.mock("@/features/file-management/content-shell", () => ({
  ContentShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock("@/features/user-profile/queries", () => ({
  userProfileQueryOptions: () => ({
    queryKey: ["profile"],
    queryFn: async () => ({ username: "synthetic-owner", preferred_language: "zh-CN" }),
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
  listExplanations: vi.fn(),
  listWeaknesses: vi.fn(),
  getWeakness: vi.fn(),
  getExplanation: vi.fn(),
  getExplanationCard: vi.fn(),
  getKnowledgeRun: vi.fn(),
  lookupKnowledgeRun: vi.fn(),
  createExplanation: vi.fn(),
  regenerateExplanation: vi.fn(),
}));
vi.mock("./card-content", () => ({ CardContent: () => <div>已保存卡片</div> }));
vi.mock("./card-sources", () => ({ CardSources: () => null }));
vi.mock("./review-history", () => ({ ReviewHistory: () => null }));
vi.mock("./knowledge-status", () => ({
  KnowledgeStatus: ({ run }: { run: KnowledgeRunView }) => (
    <p>
      当前任务 {run.id} {run.status}
    </p>
  ),
}));
const finished: KnowledgeRunView = {
  id: "run-old",
  explanation_id: syntheticCard.explanation_id,
  operation: "generate",
  status: "succeeded",
  stage: "succeeded",
  attempt_count: 1,
  retryable: false,
  error_key: null,
  result_ref: {
    type: "card",
    id: syntheticCard.id,
    explanation_id: syntheticCard.explanation_id,
    version: 1,
  },
  request_key: "old-key",
  input_digest: "old-digest",
};
const pending: KnowledgeRunView = {
  ...finished,
  id: "run-new",
  operation: "regenerate",
  status: "pending",
  stage: "pending",
  result_ref: null,
};
const detail: ExplanationDetail = {
  id: syntheticCard.explanation_id,
  weakness_id: syntheticWeakness.id,
  topic: syntheticWeakness.title,
  version: 3,
  config: {
    topic: syntheticWeakness.title,
    source_mode: "general",
    foundation: "know_concept",
    depth: "systematic",
  },
  active_card_version: 1,
  source_available: true,
  created_at: "2026-10-03T00:00:00Z",
  updated_at: "2026-10-03T00:00:00Z",
  reviews: [],
  card_versions: [1],
  card: syntheticCard,
  run: finished,
};
beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  const meta = { page: 1, page_size: 20, total: 0, total_pages: 0 };
  vi.mocked(api.listExplanations).mockResolvedValue({ data: [], meta });
  vi.mocked(api.listWeaknesses).mockResolvedValue({ data: [], meta });
  vi.mocked(api.getWeakness).mockResolvedValue({
    ...syntheticWeakness,
    source_mode: "general",
    knowledge_base_id: null,
    file_ids: [],
    card_versions: [1],
    card: syntheticCard,
    evidence: [],
    events: [],
    reviews: [],
  });
  vi.mocked(api.getExplanation).mockResolvedValue(detail);
  vi.mocked(api.getExplanationCard).mockResolvedValue(syntheticCard);
  vi.mocked(api.getKnowledgeRun).mockResolvedValue(finished);
  vi.mocked(api.regenerateExplanation).mockResolvedValue({
    data: { explanation: detail, run: pending },
    message: "已入队",
  });
});
afterEach(() => {
  cleanup();
  sessionStorage.clear();
});
function mount(ui: React.ReactNode) {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      {ui}
    </QueryClientProvider>,
  );
}
it("选择已有正式难点使用真实绑定精讲regenerate契约，保持用户基础/深度配置", async () => {
  mount(
    <ExplanationPage
      weaknessId={syntheticWeakness.id}
      weaknessVersion={syntheticWeakness.version}
    />,
  );
  await waitFor(() => expect(screen.getByRole("button", { name: "开始精讲" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "用过但不熟" }));
  fireEvent.click(screen.getByRole("button", { name: "深入原理" }));
  fireEvent.click(screen.getByRole("button", { name: "开始精讲" }));
  await waitFor(() => expect(api.regenerateExplanation).toHaveBeenCalledTimes(1));
  expect(api.regenerateExplanation).toHaveBeenCalledWith(detail.id, {
    expected_version: detail.version,
    request_key: expect.any(String),
    config: {
      topic: syntheticWeakness.title,
      source_mode: "general",
      knowledge_base_id: null,
      file_ids: [],
      foundation: "used_unfamiliar",
      depth: "deep",
    },
  });
  expect(api.createExplanation).not.toHaveBeenCalled();
  await waitFor(() =>
    expect(navigation.push).toHaveBeenCalledWith(
      `/learning/explanation/${detail.id}?run=${pending.id}`,
    ),
  );
});
it("刷新旧URL run时当前权威任务R2覆盖已完成R1，卡片历史仍单独保留", async () => {
  vi.mocked(api.getExplanation).mockResolvedValue({ ...detail, run: pending });
  mount(<ExplanationDetailPage id={detail.id} runId={finished.id} />);
  await waitFor(() => expect(screen.getByText("当前任务 run-new pending")).toBeVisible());
  expect(screen.queryByText("当前任务 run-old succeeded")).not.toBeInTheDocument();
  expect(screen.getByText("已保存卡片")).toBeVisible();
});
it("再生响应丢失持久UUID且刷新通过lookup恢复真实新任务", async () => {
  vi.mocked(api.regenerateExplanation).mockRejectedValue(
    new ApiError("网络连接失败", { errorKey: "NETWORK_ERROR" }),
  );
  vi.mocked(api.lookupKnowledgeRun).mockRejectedValue(new ApiError("暂未找到", { status: 404 }));
  const first = mount(<ExplanationDetailPage id={detail.id} runId={finished.id} />);
  await waitFor(() => expect(screen.getByRole("button", { name: "重新生成" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "重新生成" }));
  await waitFor(() => expect(api.regenerateExplanation).toHaveBeenCalledTimes(1));
  const requestKey = vi.mocked(api.regenerateExplanation).mock.calls[0][1].request_key;
  await waitFor(() =>
    expect(readKnowledgeRequest(sessionStorage, "synthetic-owner", detail.id)).toBe(requestKey),
  );
  first.unmount();
  vi.mocked(api.lookupKnowledgeRun).mockResolvedValue(pending);
  vi.mocked(api.getKnowledgeRun).mockImplementation(async (id) =>
    id === pending.id ? pending : finished,
  );
  mount(<ExplanationDetailPage id={detail.id} runId={finished.id} />);
  await waitFor(() =>
    expect(navigation.replace).toHaveBeenCalledWith(
      `/learning/explanation/${detail.id}?run=${pending.id}`,
    ),
  );
  await waitFor(() => expect(screen.getByText("当前任务 run-new pending")).toBeVisible());
  expect(readKnowledgeRequest(sessionStorage, "synthetic-owner", detail.id)).toBe("");
});
it("lookup metadata按owner/target隔离且不包含学习正文", () => {
  const key = "12345678-1234-1234-1234-123456789abc";
  writeKnowledgeRequest(sessionStorage, "synthetic-owner", detail.id, key);
  expect(readKnowledgeRequest(sessionStorage, "other-owner", detail.id)).toBe("");
  expect(readKnowledgeRequest(sessionStorage, "synthetic-owner", "other-target")).toBe("");
  expect(sessionStorage.getItem(sessionStorage.key(0)!)).toBe(key);
});

it("详情组件切到另一个精讲时读取新的URL任务，不沿用旧run指针", async () => {
  const nextId = "another-explanation";
  const nextRun = { ...pending, id: "another-run", explanation_id: nextId };
  vi.mocked(api.getExplanation).mockImplementation(async (id) => ({
    ...detail,
    id,
    topic: id === nextId ? "另一个精讲" : detail.topic,
    run: null,
  }));
  vi.mocked(api.getKnowledgeRun).mockImplementation(async (id) =>
    id === nextRun.id ? nextRun : finished,
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <ExplanationDetailPage id={detail.id} runId={finished.id} />
    </QueryClientProvider>,
  );
  await screen.findByText("当前任务 run-old succeeded");
  view.rerender(
    <QueryClientProvider client={client}>
      <ExplanationDetailPage id={nextId} runId={nextRun.id} />
    </QueryClientProvider>,
  );
  await screen.findByText("当前任务 another-run pending");
  expect(api.getKnowledgeRun).toHaveBeenCalledWith(nextRun.id);
  expect(screen.queryByText("当前任务 run-old succeeded")).not.toBeInTheDocument();
});

it("离开旧精讲后再生的迟到响应不能把页面跳回旧目标", async () => {
  let finish!: (value: Awaited<ReturnType<typeof api.regenerateExplanation>>) => void;
  vi.mocked(api.regenerateExplanation).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <ExplanationDetailPage id={detail.id} />
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.getByRole("button", { name: "重新生成" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "重新生成" }));
  await waitFor(() => expect(api.regenerateExplanation).toHaveBeenCalled());
  view.rerender(
    <QueryClientProvider client={client}>
      <ExplanationDetailPage id="another-explanation" />
    </QueryClientProvider>,
  );
  await act(async () => {
    finish({ data: { explanation: detail, run: pending }, message: "ok" });
  });
  expect(navigation.replace).not.toHaveBeenCalledWith(
    `/learning/explanation/${detail.id}?run=${pending.id}`,
  );
});
