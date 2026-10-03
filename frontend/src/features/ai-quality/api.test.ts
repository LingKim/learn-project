import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { authenticatedAccessToken } from "@/features/auth/auth-provider";
import { ApiError } from "@/lib/api/errors";
import * as api from "./api";
vi.mock("@/features/auth/auth-provider", () => ({ authenticatedAccessToken: vi.fn() }));
const NativeRequest = globalThis.Request;
beforeEach(() => {
  vi.mocked(authenticatedAccessToken).mockResolvedValue("quality-access");
  // Node Request 不接受浏览器的相对 URL；只在测试提供者中补齐浏览器地址解析。
  vi.stubGlobal(
    "Request",
    class extends NativeRequest {
      constructor(input: RequestInfo | URL, init?: RequestInit) {
        super(
          typeof input === "string" ? new URL(input, "http://localhost").toString() : input,
          init,
        );
      }
    },
  );
});
afterEach(() => vi.unstubAllGlobals());
it("全部17个真实operation经过generated SDK、no-store与统一协议", async () => {
  const transport = vi.fn().mockImplementation((request: Request) => {
    const page =
      request.method === "GET" &&
      (request.url.endsWith("/ai-quality-cases") || request.url.endsWith("/cases"));
    const status =
      request.method === "POST" && request.url.endsWith("/ai-quality-cases") ? 201 : 200;
    return Promise.resolve(
      new Response(
        JSON.stringify({
          code: status,
          message: "ok",
          data: page ? [] : {},
          ...(page ? { meta: { page: 1, page_size: 20, total: 0, total_pages: 0 } } : {}),
        }),
        { status, headers: { "Content-Type": "application/json" } },
      ),
    );
  });
  vi.stubGlobal("fetch", transport);
  const body = { expected_version: 1 };
  const grant = { ...body, expected_grant_version: 2 };
  const run = [
    () => api.listCases(),
    () => api.getCase("case"),
    () =>
      api.createCase({
        source_type: "learning_turn",
        source_id: "turn",
        trace_id: "trace",
        request_key: "request",
        category: "other",
        description: "问题",
        basic_access_confirmed: true,
      }),
    () => api.addMessage("case", { ...body, content: "补充" }),
    () => api.decideGrant("case", "grant", { ...grant, approved: false }),
    () => api.revokeGrant("case", "grant", grant),
    () => api.withdrawCase("case", body),
    () => api.closeCase("case", body),
    () => api.getOverview(),
    () => api.listAdminCases(),
    () => api.getAdminCase("case"),
    () =>
      api.getSnapshot("case", { grant_id: "grant", expected_grant_version: 2, fields: ["query"] }),
    () => api.assignCase("case", { ...body, assignee_id: null }),
    () =>
      api.requestAccess("case", {
        ...body,
        reason: "检查候选",
        chunk_ids: ["chunk"],
        duration_days: 1,
      }),
    () =>
      api.replayCase("case", {
        ...grant,
        grant_id: "grant",
        mode: "fts_only",
        target_chunk_ids: [],
      }),
    () => api.addAdminMessage("case", { ...body, content: "内部记录", visibility: "admin" }),
    () => api.transitionCase("case", { ...body, status: "triaging" }),
  ];
  for (const call of run) await call();
  expect(transport).toHaveBeenCalledTimes(17);
  const requests = transport.mock.calls.map(([request]) => request as Request);
  expect(
    new Set(requests.map((request) => `${request.method} ${new URL(request.url).pathname}`)).size,
  ).toBe(17);
  for (const request of requests) {
    expect(request.cache).toBe("no-store");
    expect(request.credentials).toBe("include");
    expect(request.headers.get("Authorization")).toBe("Bearer quality-access");
    expect(request.url).toContain("/api/backend/api/v1/");
  }
  expect(requests.find((request) => request.url.includes("/snapshot"))?.url).toContain(
    "expected_grant_version=2",
  );
});
it("跨用户与普通账号拒绝保持ApiError，错误响应不会成为成功数据", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            code: 403,
            status: 403,
            message: "无权限",
            error_key: "QUALITY_ADMIN_REQUIRED",
            type: "about:blank",
            title: "无权限",
            detail: "无权限",
          }),
          { status: 403, headers: { "Content-Type": "application/json" } },
        ),
      ),
    ),
  );
  await expect(api.getAdminCase("other-owner-case")).rejects.toBeInstanceOf(ApiError);
  await expect(api.getAdminCase("other-owner-case")).rejects.toMatchObject({
    status: 403,
    errorKey: "QUALITY_ADMIN_REQUIRED",
  });
});
it("查询取消signal穿过SDK，畸形响应不能绕过protocol", async () => {
  const transport = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ data: {} }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", transport);
  const abort = new AbortController();
  await expect(api.getCase("case", abort.signal)).rejects.toMatchObject({
    errorKey: "API_CONTRACT_MISMATCH",
  });
  const request = transport.mock.calls[0][0] as Request;
  abort.abort();
  expect(request.signal.aborted).toBe(true);
});
