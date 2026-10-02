import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LearningPage, answerError } from "./learning-page";
import { learningKeys, conversationQueryOptions, sendQuestionMutationOptions } from "./queries";
import * as api from "./api";

vi.mock("./api", () => ({
  getLearningConsent: vi.fn(),
  confirmLearningConsent: vi.fn(),
  listConversations: vi.fn(),
  createConversation: vi.fn(),
  getConversation: vi.fn(),
  renameConversation: vi.fn(),
  deleteConversation: vi.fn(),
  sendQuestion: vi.fn(),
  setFeedback: vi.fn(),
}));
vi.mock("@/features/file-management/api", () => ({
  listKnowledgeBases: vi
    .fn()
    .mockResolvedValue({ data: [], meta: { page: 1, page_size: 100, total: 0, total_pages: 0 } }),
  listKnowledgeFiles: vi.fn(),
}));
vi.mock("@/features/file-management/content-shell", () => ({
  ContentShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
const conversation: api.ConversationView = {
  id: "conversation",
  mode: "general",
  knowledge_base_id: null,
  file_ids: [],
  title: "合成问题",
  created_at: "2026-10-02T00:00:00Z",
  updated_at: "2026-10-02T00:00:00Z",
};
const turn: api.TurnView = {
  id: "turn",
  request_key: "key",
  language: "zh",
  question: "合成问题",
  status: "succeeded",
  answer: "合成回答",
  refused: false,
  source_label: "模型通用知识",
  citations: [],
  trace_id: null,
  trace_complete: false,
  error_code: null,
  feedback: null,
  created_at: "2026-10-02T00:00:00Z",
};
function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <LearningPage />
    </QueryClientProvider>,
  );
  return client;
}
afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getLearningConsent).mockResolvedValue({
    confirmed: true,
    terms_version: "learning-v1",
    notice: "问题和资料将发送千问",
  });
  vi.mocked(api.listConversations).mockResolvedValue({
    data: [],
    meta: { page: 1, page_size: 20, total: 0, total_pages: 0 },
  });
  vi.mocked(api.createConversation).mockResolvedValue({ data: conversation, message: "成功" });
  vi.mocked(api.getConversation).mockResolvedValue({ conversation, turns: [] });
  vi.mocked(api.sendQuestion).mockResolvedValue({ data: turn, message: "成功" });
});
describe("学习快速回答交互", () => {
  it("mode changes clear unrelated input", async () => {
    mount();
    fireEvent.change(screen.getByLabelText("您的问题"), { target: { value: "旧资料问题" } });
    fireEvent.click(screen.getByRole("button", { name: "通用模式" }));
    expect(screen.getByLabelText("您的问题")).toHaveValue("");
    expect(screen.queryByRole("combobox", { name: "知识库" })).not.toBeInTheDocument();
    await screen.findByText("回答来自模型通用知识，不使用您的资料。");
  });
  it("requires explicit consent with checkbox unchecked before sending", async () => {
    vi.mocked(api.getLearningConsent).mockResolvedValue({
      confirmed: false,
      terms_version: "learning-v1",
      notice: "问题和资料将发送千问",
    });
    mount();
    fireEvent.click(screen.getByRole("button", { name: "通用模式" }));
    fireEvent.change(screen.getByLabelText("您的问题"), { target: { value: "问题" } });
    await waitFor(() => expect(screen.getByRole("button", { name: "发送问题" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    expect(screen.getByRole("button", { name: "确认" })).toBeDisabled();
    expect(api.sendQuestion).not.toHaveBeenCalled();
  });
  it("preserves question and key for a retry after model failure", async () => {
    vi.mocked(api.sendQuestion).mockRejectedValueOnce(new Error("failure"));
    mount();
    fireEvent.click(screen.getByRole("button", { name: "通用模式" }));
    fireEvent.change(screen.getByLabelText("您的问题"), { target: { value: "合成问题" } });
    await waitFor(() => expect(screen.getByRole("button", { name: "发送问题" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));
    await screen.findByRole("alert");
    expect(screen.getByLabelText("继续提问")).toHaveValue("合成问题");
    const key = vi.mocked(api.sendQuestion).mock.calls[0][1].request_key;
    await waitFor(() => expect(screen.getByRole("button", { name: "发送问题" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));
    await waitFor(() => expect(api.sendQuestion).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.sendQuestion).mock.calls[1][1].request_key).toBe(key);
  });
  it("shows unavailable citations without allowing a stale preview", async () => {
    vi.mocked(api.listConversations).mockResolvedValue({
      data: [conversation],
      meta: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    vi.mocked(api.getConversation).mockResolvedValue({
      conversation,
      turns: [{ ...turn, citations: [{ number: 1, available: false, evidence: null }] }],
    });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "合成问题" }));
    expect(await screen.findByRole("button", { name: "[1] 来源已失效" })).toBeDisabled();
    expect(screen.getByText("模型通用知识")).toBeInTheDocument();
  });
  it("isolates detail keys and refreshes failed requests", async () => {
    expect(conversationQueryOptions("").enabled).toBe(false);
    expect(learningKeys.detail("one")).not.toEqual(learningKeys.detail("two"));
    const client = new QueryClient();
    const refresh = vi.spyOn(client, "invalidateQueries").mockResolvedValue();
    const options = sendQuestionMutationOptions(client);
    await options.onSettled?.(
      undefined,
      new Error("failed"),
      { id: "one", body: { question: "问题", request_key: "key" } },
      undefined,
      {} as never,
    );
    expect(refresh).toHaveBeenCalledWith({ queryKey: learningKeys.detail("one") });
    expect(answerError("ANSWER_CITATION_INVALID")).toContain("引用校验");
  });
});
