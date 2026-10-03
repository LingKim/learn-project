import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { authenticatedAccessToken } from "@/features/auth/auth-provider";
import { createExplanation, getKnowledgeRun, patchWeakness } from "./api";
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
it("真实SDK生成202任务保留鉴权、no-store和省略/null/数组presence", async () => {
  const transport = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        code: 202,
        message: "已入队",
        data: { explanation: { id: "exp" }, run: { id: "run", status: "pending" } },
      }),
      { status: 202, headers: { "content-type": "application/json" } },
    ),
  );
  vi.stubGlobal("fetch", transport);
  const body = {
    topic: "合成概念",
    request_key: "synthetic-key",
    target_job: null,
    target_skills: [],
  };
  expect((await createExplanation(body)).data.run.status).toBe("pending");
  const request = transport.mock.calls[0][0] as Request;
  expect(request.url).toContain("/api/backend/api/v1/learning/explanations");
  expect(request.cache).toBe("no-store");
  expect(request.headers.get("Authorization")).toBe("Bearer synthetic-access");
  expect(JSON.parse(await request.clone().text())).toEqual(body);
});
it("并发版本冲突保持ApiError和HTTP一致，写请求不自动重试", async () => {
  const transport = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        status: 409,
        code: 409,
        title: "版本冲突",
        detail: "读取最新版本",
        message: "读取最新版本",
        error_key: "LEARNING_ASSET_VERSION_CONFLICT",
      }),
      { status: 409, headers: { "content-type": "application/json" } },
    ),
  );
  vi.stubGlobal("fetch", transport);
  await expect(
    patchWeakness("weakness", { expected_version: 1, title: "合成新名称" }),
  ).rejects.toMatchObject({ status: 409, errorKey: "LEARNING_ASSET_VERSION_CONFLICT" });
  expect(transport).toHaveBeenCalledTimes(1);
});
it("failed任务只读查询呈现真实状态，不触发生成", async () => {
  const transport = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        code: 200,
        message: "ok",
        data: { id: "run", status: "failed", error_key: "KNOWLEDGE_OUTPUT_INVALID" },
      }),
      { headers: { "content-type": "application/json" } },
    ),
  );
  vi.stubGlobal("fetch", transport);
  expect((await getKnowledgeRun("run")).status).toBe("failed");
  expect((transport.mock.calls[0][0] as Request).method).toBe("GET");
  expect(transport).toHaveBeenCalledTimes(1);
});
