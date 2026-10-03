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
  streamQuestion: vi.fn(),
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
  vi.mocked(api.streamQuestion).mockImplementation(async (_id, body, _signal, receive) => {
    receive({
      type: "started",
      turn: { ...turn, request_key: body.request_key, status: "processing", answer: null },
    });
    receive({ type: "delta", delta: "合成" });
    receive({ type: "completed", turn: { ...turn, request_key: body.request_key } });
  });
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
  it("sends on Enter, preserves Shift Enter and IME composition, and respects source validation", async () => {
    mount();
    const draft = screen.getByLabelText("您的问题");
    fireEvent.change(draft, { target: { value: "资料问题" } });
    fireEvent.keyDown(draft, { key: "Enter" });
    expect(api.createConversation).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "通用模式" }));
    fireEvent.change(draft, { target: { value: "合成问题" } });
    fireEvent.keyDown(draft, { key: "Enter", shiftKey: true });
    fireEvent.keyDown(draft, { key: "Enter", isComposing: true });
    expect(api.createConversation).not.toHaveBeenCalled();
    expect(draft).toHaveValue("合成问题");
    fireEvent.keyDown(draft, { key: "Enter" });
    await screen.findByText("合成回答");
    expect(api.createConversation).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText("继续提问")).toHaveValue("");
  });
  it("immediately echoes the question before conversation creation, without consent or language controls", async () => {
    let finish!: (value: Awaited<ReturnType<typeof api.createConversation>>) => void;
    vi.mocked(api.createConversation).mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    mount();
    fireEvent.click(screen.getByRole("button", { name: "通用模式" }));
    fireEvent.change(screen.getByLabelText("您的问题"), { target: { value: "立即出现" } });
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));
    expect(screen.getByText("立即出现")).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "正在回答" })).toBeInTheDocument();
    expect(screen.getByLabelText("继续提问")).toHaveValue("");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "回答语言" })).not.toBeInTheDocument();
    expect(api.getLearningConsent).not.toHaveBeenCalled();
    await waitFor(() => expect(finish).toBeTypeOf("function"));
    finish({ data: conversation, message: "成功" });
    await screen.findByText("合成回答");
    expect(vi.mocked(api.streamQuestion).mock.calls[0][1]).not.toHaveProperty("language");
  });
  it("discards partial output on failure and retries the same key without duplicate questions", async () => {
    vi.mocked(api.streamQuestion).mockImplementationOnce(async (_id, body, _signal, receive) => {
      receive({
        type: "started",
        turn: {
          ...turn,
          question: body.question,
          request_key: body.request_key,
          status: "processing",
          answer: null,
        },
      });
      receive({ type: "delta", delta: "不可信临时正文" });
      throw new Error("disconnect");
    });
    mount();
    fireEvent.click(screen.getByRole("button", { name: "通用模式" }));
    fireEvent.change(screen.getByLabelText("您的问题"), { target: { value: "合成问题" } });
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));
    fireEvent.click(await screen.findByRole("button", { name: "重试回答" }));
    await screen.findByText("合成回答");
    expect(screen.queryByText("不可信临时正文")).not.toBeInTheDocument();
    expect(screen.getAllByText("合成问题")).toHaveLength(1);
    expect(vi.mocked(api.streamQuestion).mock.calls[1][1].request_key).toBe(
      vi.mocked(api.streamQuestion).mock.calls[0][1].request_key,
    );
  });
  it("shows incremental output and ignores late events after switching conversations", async () => {
    let receive!: (event: api.AnswerStreamEvent) => void;
    let complete!: () => void;
    vi.mocked(api.streamQuestion).mockImplementation((_id, _body, _signal, callback) => {
      receive = callback;
      return new Promise((resolve) => {
        complete = resolve;
      });
    });
    mount();
    fireEvent.click(screen.getByRole("button", { name: "通用模式" }));
    fireEvent.change(screen.getByLabelText("您的问题"), { target: { value: "合成问题" } });
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));
    await waitFor(() => expect(receive).toBeTypeOf("function"));
    receive({ type: "delta", delta: "逐步出现" });
    await screen.findByText("逐步出现");
    fireEvent.click(screen.getByRole("button", { name: "新建会话" }));
    receive({ type: "delta", delta: "迟到消息" });
    complete();
    await waitFor(() => expect(screen.queryByText("逐步出现")).not.toBeInTheDocument());
    expect(screen.queryByText(/迟到消息/)).not.toBeInTheDocument();
  });
  it("keeps live incremental text when a processing detail refresh arrives", async () => {
    let receive!: (event: api.AnswerStreamEvent) => void;
    let complete!: () => void;
    let requestKey = "";
    vi.mocked(api.streamQuestion).mockImplementation((_id, body, _signal, callback) => {
      receive = callback;
      requestKey = body.request_key;
      return new Promise((resolve) => {
        complete = resolve;
      });
    });
    const client = mount();
    fireEvent.click(screen.getByRole("button", { name: "通用模式" }));
    fireEvent.change(screen.getByLabelText("您的问题"), { target: { value: "合成问题" } });
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));
    await waitFor(() => expect(receive).toBeTypeOf("function"));
    receive({
      type: "started",
      turn: { ...turn, request_key: requestKey, status: "processing", answer: null },
    });
    receive({ type: "delta", delta: "第一段增量" });
    await screen.findByText("第一段增量");
    client.setQueryData(learningKeys.detail("conversation"), {
      conversation,
      turns: [{ ...turn, request_key: requestKey, status: "processing", answer: null }],
    });
    await waitFor(() => expect(screen.getByText("第一段增量")).toBeInTheDocument());
    receive({ type: "delta", delta: "第二段增量" });
    await screen.findByText("第一段增量第二段增量");
    receive({ type: "completed", turn: { ...turn, request_key: requestKey } });
    complete();
    await screen.findByText("合成回答");
    expect(screen.queryByText("第一段增量第二段增量")).not.toBeInTheDocument();
  });
  it("does not move readers away from history and offers return to bottom", async () => {
    let receive!: (event: api.AnswerStreamEvent) => void;
    let complete!: () => void;
    vi.mocked(api.streamQuestion).mockImplementation((_id, _body, _signal, callback) => {
      receive = callback;
      return new Promise((resolve) => {
        complete = resolve;
      });
    });
    mount();
    fireEvent.click(screen.getByRole("button", { name: "通用模式" }));
    fireEvent.change(screen.getByLabelText("您的问题"), { target: { value: "合成问题" } });
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));
    await waitFor(() => expect(receive).toBeTypeOf("function"));
    const messages = screen.getByRole("log", { name: "消息列表" });
    Object.defineProperties(messages, {
      scrollHeight: { configurable: true, value: 1000 },
      clientHeight: { configurable: true, value: 300 },
    });
    messages.scrollTop = 80;
    fireEvent.scroll(messages);
    receive({ type: "delta", delta: "增量输出" });
    await screen.findByText("增量输出");
    expect(messages.scrollTop).toBe(80);
    fireEvent.click(screen.getByRole("button", { name: "回到底部" }));
    expect(messages.scrollTop).toBe(1000);
    fireEvent.click(screen.getByRole("button", { name: "新建会话" }));
    complete();
  });
  it("aborts active transport on unmount", async () => {
    let signal!: AbortSignal;
    let complete!: () => void;
    vi.mocked(api.streamQuestion).mockImplementation((_id, _body, currentSignal) => {
      signal = currentSignal;
      return new Promise((resolve) => {
        complete = resolve;
      });
    });
    mount();
    fireEvent.click(screen.getByRole("button", { name: "通用模式" }));
    fireEvent.change(screen.getByLabelText("您的问题"), { target: { value: "合成问题" } });
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));
    await waitFor(() => expect(signal).toBeDefined());
    cleanup();
    expect(signal.aborted).toBe(true);
    complete();
  });
  it("keeps icon feedback connected and copies completed content", async () => {
    vi.mocked(api.listConversations).mockResolvedValue({
      data: [conversation],
      meta: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    vi.mocked(api.getConversation).mockResolvedValue({ conversation, turns: [turn] });
    vi.mocked(api.setFeedback).mockImplementation(async (_id, _turnId, body) => {
      const updated = { ...turn, feedback: body.feedback ?? null };
      vi.mocked(api.getConversation).mockResolvedValue({ conversation, turns: [updated] });
      return { data: updated, message: "成功" };
    });
    const copy = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: copy },
    });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "合成问题" }));
    const helpful = await screen.findByRole("button", { name: "有帮助" });
    expect(helpful).toHaveAttribute("title", "有帮助");
    expect(helpful).not.toHaveTextContent("有帮助");
    fireEvent.click(helpful);
    await waitFor(() =>
      expect(api.setFeedback).toHaveBeenCalledWith("conversation", "turn", { feedback: "helpful" }),
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "有帮助" })).toHaveAttribute(
        "aria-pressed",
        "true",
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "有帮助" }));
    await waitFor(() =>
      expect(api.setFeedback).toHaveBeenLastCalledWith("conversation", "turn", { feedback: null }),
    );
    fireEvent.click(screen.getByRole("button", { name: "复制回答" }));
    await waitFor(() => expect(copy).toHaveBeenCalledWith("合成回答"));
    expect(screen.queryByRole("button", { name: "生成笔记" })).not.toBeInTheDocument();
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
    expect(answerError("ANSWER_MARKDOWN_INVALID")).toBe("回答格式未通过校验，请重试。");
  });
});
