import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { authenticatedAccessToken } from "@/features/auth/auth-provider";
import {
  learningAnswersCreate,
  learningAnswersStream,
  learningConversationsList,
} from "@/lib/api/generated/sdk.gen";
import { listConversations, sendQuestion, streamQuestion } from "./api";
vi.mock("@/features/auth/auth-provider", () => ({ authenticatedAccessToken: vi.fn() }));
vi.mock("@/lib/api/generated/sdk.gen", () => ({
  learningAnswersCreate: vi.fn(),
  learningAnswersStream: vi.fn(),
  learningConversationsList: vi.fn(),
}));
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(authenticatedAccessToken).mockResolvedValue("test-access");
});
it("uses shared page protocol and scoped auth", async () => {
  vi.mocked(learningConversationsList).mockResolvedValue({
    data: {
      code: 200,
      message: "ok",
      data: [],
      meta: { page: 2, page_size: 20, total: 0, total_pages: 0 },
    },
    error: undefined,
    request: new Request("http://localhost"),
    response: new Response(null, { status: 200 }),
  });
  expect((await listConversations(2)).meta.page).toBe(2);
  expect(learningConversationsList).toHaveBeenCalledWith(
    expect.objectContaining({
      baseUrl: "/api/backend",
      headers: { Authorization: "Bearer test-access" },
      query: { page: 2, page_size: 20 },
    }),
  );
});
it("keeps upstream failures as ApiError with no success result", async () => {
  vi.mocked(learningAnswersCreate).mockRejectedValue({
    type: "about:blank",
    title: "上游服务异常",
    status: 502,
    code: 502,
    message: "请重试",
    data: null,
    detail: "请重试",
    error_key: "ANSWER_OUTPUT_INVALID",
  });
  await expect(sendQuestion("id", { request_key: "key", question: "问题" })).rejects.toMatchObject({
    status: 502,
  });
});

it("streams real generated SDK packets once, including split Unicode and terminal replacement", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/generated/sdk.gen")>(
    "@/lib/api/generated/sdk.gen",
  );
  vi.mocked(learningAnswersStream).mockImplementation(actual.learningAnswersStream);
  const events = [
    { type: "started", turn: { ...syntheticTurn, status: "processing", answer: null } },
    { type: "delta", delta: "你好" },
    { type: "completed", turn: syntheticTurn },
  ];
  const wire = new TextEncoder().encode(
    events.map((event) => `data: ${JSON.stringify(event)}\r\n\r\n`).join(""),
  );
  const transport = vi.fn().mockResolvedValue(
    new Response(
      new ReadableStream({
        start(controller) {
          for (let index = 0; index < wire.length; index += 1)
            controller.enqueue(wire.slice(index, index + 1));
          controller.close();
        },
      }),
      { headers: { "content-type": "text/event-stream" } },
    ),
  );
  vi.stubGlobal("fetch", transport);
  const receive = vi.fn();
  await streamQuestion(
    "id",
    { question: "问题", request_key: "key" },
    new AbortController().signal,
    receive,
  );
  expect(receive.mock.calls.map(([event]) => event)).toEqual(events);
  expect(transport).toHaveBeenCalledTimes(1);
  expect(learningAnswersStream).toHaveBeenCalledWith(
    expect.objectContaining({
      sseMaxRetryAttempts: 1,
      headers: { Authorization: "Bearer test-access" },
    }),
  );
});
it("rejects failed events, premature EOF and HTTP errors without automatically resubmitting", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/generated/sdk.gen")>(
    "@/lib/api/generated/sdk.gen",
  );
  vi.mocked(learningAnswersStream).mockImplementation(actual.learningAnswersStream);
  const transport = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(
        'data: {"type":"failed","error_code":"ANSWER_CITATION_INVALID","message":"引用无效"}\n\n',
        { headers: { "content-type": "text/event-stream" } },
      ),
    )
    .mockResolvedValueOnce(
      new Response('data: {"type":"delta","delta":"未完成"}\n\n', {
        headers: { "content-type": "text/event-stream" },
      }),
    )
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          status: 403,
          code: 403,
          title: "拒绝",
          detail: "无权访问",
          message: "无权访问",
        }),
        { status: 403 },
      ),
    );
  vi.stubGlobal("fetch", transport);
  await expect(
    streamQuestion(
      "id",
      { question: "问题", request_key: "key" },
      new AbortController().signal,
      vi.fn(),
    ),
  ).rejects.toMatchObject({ errorKey: "ANSWER_CITATION_INVALID" });
  await expect(
    streamQuestion(
      "id",
      { question: "问题", request_key: "key" },
      new AbortController().signal,
      vi.fn(),
    ),
  ).rejects.toMatchObject({ errorKey: "ANSWER_STREAM_INTERRUPTED" });
  await expect(
    streamQuestion(
      "id",
      { question: "问题", request_key: "key" },
      new AbortController().signal,
      vi.fn(),
    ),
  ).rejects.toMatchObject({ status: 403 });
  expect(transport).toHaveBeenCalledTimes(3);
});
const syntheticTurn = {
  id: "turn",
  request_key: "key",
  language: "zh",
  question: "问题",
  status: "succeeded",
  answer: "完整回答",
  refused: false,
  source_label: "模型通用知识",
  citations: [],
  trace_id: null,
  trace_complete: false,
  error_code: null,
  feedback: null,
  created_at: "2026-10-03T00:00:00Z",
};

afterEach(() => vi.unstubAllGlobals());
