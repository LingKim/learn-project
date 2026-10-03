import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { authenticatedAccessToken } from "@/features/auth/auth-provider";
import { requestPracticePlan, getPracticeRun, submitPracticeAnswer } from "./api";
import { pendingRun } from "./fixtures.test-support";
vi.mock("@/features/auth/auth-provider", () => ({ authenticatedAccessToken: vi.fn() }));
beforeEach(() => {
  vi.mocked(authenticatedAccessToken).mockResolvedValue("synthetic-access");
  const NativeRequest = Request;
  vi.stubGlobal(
    "Request",
    class BrowserRequest extends NativeRequest {
      constructor(input: RequestInfo | URL, init?: RequestInit) {
        super(typeof input === "string" ? new URL(input, "http://localhost") : input, init);
      }
    },
  );
});
afterEach(() => vi.unstubAllGlobals());
it("真实SDK保留202、no-store、私有鉴权以及后端响应解包", async () => {
  const transport = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ code: 202, message: "已入队", data: pendingRun }), {
      status: 202,
      headers: { "content-type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", transport);
  const result = await requestPracticePlan("set", { expected_version: 1, request_key: "key" });
  expect(result.data.status).toBe("pending");
  expect(result.message).toBe("已入队");
  expect(transport).toHaveBeenCalledTimes(1);
  const request = transport.mock.calls[0][0] as Request;
  expect(request.url).toContain("/api/backend/api/v1/learning/practice/sets/set/plan");
  expect(request.headers.get("Authorization")).toBe("Bearer synthetic-access");
  expect(request.cache).toBe("no-store");
  expect(JSON.parse(await request.clone().text())).toEqual({
    expected_version: 1,
    request_key: "key",
  });
});
it("版本冲突映射ApiError，不能返回成功或自动重试提交", async () => {
  const transport = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        status: 409,
        code: 409,
        title: "版本冲突",
        detail: "读取最新版本",
        message: "读取最新版本",
        error_key: "PRACTICE_VERSION_CONFLICT",
      }),
      { status: 409, headers: { "content-type": "application/json" } },
    ),
  );
  vi.stubGlobal("fetch", transport);
  await expect(
    submitPracticeAnswer("attempt", "q", {
      expected_version: 1,
      answer_version: 1,
      request_key: "key",
    }),
  ).rejects.toMatchObject({ status: 409, errorKey: "PRACTICE_VERSION_CONFLICT" });
  expect(transport).toHaveBeenCalledTimes(1);
});
it("状态查询通过只读GET返回真实失败状态，不重新调用模型", async () => {
  const transport = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        code: 200,
        message: "ok",
        data: {
          ...pendingRun,
          status: "failed",
          error_key: "PRACTICE_GRADE_INVALID",
          retryable: true,
        },
      }),
      { headers: { "content-type": "application/json" } },
    ),
  );
  vi.stubGlobal("fetch", transport);
  expect((await getPracticeRun("run")).status).toBe("failed");
  expect((transport.mock.calls[0][0] as Request).method).toBe("GET");
  expect(transport).toHaveBeenCalledTimes(1);
});
