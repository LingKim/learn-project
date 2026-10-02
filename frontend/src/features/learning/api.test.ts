import { beforeEach, expect, it, vi } from "vitest";
import { authenticatedAccessToken } from "@/features/auth/auth-provider";
import { learningAnswersCreate, learningConversationsList } from "@/lib/api/generated/sdk.gen";
import { listConversations, sendQuestion } from "./api";
vi.mock("@/features/auth/auth-provider", () => ({ authenticatedAccessToken: vi.fn() }));
vi.mock("@/lib/api/generated/sdk.gen", () => ({
  learningAnswersCreate: vi.fn(),
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
