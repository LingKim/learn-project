import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { authenticatedAccessToken } from "@/features/auth/auth-provider";
import * as api from "./api";

vi.mock("@/features/auth/auth-provider", () => ({ authenticatedAccessToken: vi.fn() }));
beforeEach(() => {
  vi.mocked(authenticatedAccessToken).mockResolvedValue("synthetic-admin-access");
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

const routes = [
  [
    "GET",
    "/prompt-definitions",
    () => api.listPromptDefinitions({ agent_key: "question_generator" }),
  ],
  ["GET", "/prompt-definitions/definition", () => api.getPromptDefinition("definition")],
  ["GET", "/prompt-definitions/definition/versions", () => api.listPromptVersions("definition", 2)],
  ["GET", "/prompt-versions/version", () => api.getPromptVersion("version")],
  ["GET", "/prompt-versions/version/diff", () => api.getPromptDiff("version", "historical")],
  [
    "GET",
    "/prompt-definitions/definition/audit-events",
    () => api.listPromptAuditEvents("definition"),
  ],
  [
    "POST",
    "/prompt-definitions/definition/versions",
    () =>
      api.createPromptDraft("definition", {
        expected_active_version_id: null,
        change_description: "合成测试",
      }),
  ],
  [
    "PATCH",
    "/prompt-versions/version",
    () =>
      api.patchPromptDraft("version", {
        expected_revision: 3,
        content: "合成指令",
        variables: [],
        dependencies: [],
        change_description: "合成测试",
      }),
  ],
  [
    "POST",
    "/prompt-versions/version/preview",
    () => api.previewPromptVersion("version", { variables: { request: { target_job: null } } }),
  ],
  ["POST", "/prompt-versions/version/evaluation-runs", () => api.evaluatePromptVersion("version")],
  [
    "POST",
    "/prompt-versions/version/publish",
    () =>
      api.publishPromptVersion("version", {
        expected_active_version_id: "active",
        expected_revision: 3,
      }),
  ],
  [
    "POST",
    "/prompt-definitions/definition/rollbacks",
    () =>
      api.rollbackPromptDefinition("definition", {
        expected_active_version_id: "active",
        target_version_id: "historical",
        reason: "合成回滚原因",
      }),
  ],
  [
    "POST",
    "/prompt-definitions/definition/status",
    () =>
      api.setPromptDefinitionStatus("definition", {
        expected_active_version_id: "active",
        runtime_status: "disabled",
      }),
  ],
] as const;

it.each(routes)("真实SDK %s %s携带鉴权且禁止缓存", async (method, path, call) => {
  const status = path.endsWith("/versions") && method === "POST" ? 201 : 200;
  const transport = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        code: status,
        message: "ok",
        data:
          method === "GET" &&
          (path.endsWith("definitions") ||
            path.endsWith("versions") ||
            path.endsWith("audit-events"))
            ? []
            : {},
        meta: { page: 1, page_size: 20, total: 0, total_pages: 0 },
      }),
      { status, headers: { "content-type": "application/json" } },
    ),
  );
  vi.stubGlobal("fetch", transport);
  await call();
  const request = transport.mock.calls[0][0] as Request;
  expect(request.method).toBe(method);
  expect(new URL(request.url).pathname).toBe(`/api/backend/api/v1/admin${path}`);
  expect(request.headers.get("Authorization")).toBe("Bearer synthetic-admin-access");
  expect(request.cache).toBe("no-store");
  expect(request.credentials).toBe("include");
  expect(transport).toHaveBeenCalledTimes(1);
});

it.each([401, 403, 409])("角色或版本拒绝%d经共享ApiError返回，不产生成功结果", async (status) => {
  const transport = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        status,
        code: status,
        title: "拒绝",
        detail: "请求未完成",
        message: "请求未完成",
        error_key: status === 409 ? "PROMPT_VERSION_CONFLICT" : "PROMPT_ADMIN_REQUIRED",
      }),
      { status, headers: { "content-type": "application/json" } },
    ),
  );
  vi.stubGlobal("fetch", transport);
  await expect(
    api.publishPromptVersion("version", {
      expected_active_version_id: "active",
      expected_revision: 3,
    }),
  ).rejects.toMatchObject({ status });
  expect(transport).toHaveBeenCalledTimes(1);
});

it("版本比较和分页保留实际查询参数；正文读取消费取消signal", async () => {
  const transport = vi.fn().mockImplementation(() =>
    Promise.resolve(
      new Response(JSON.stringify({ code: 200, message: "ok", data: {} }), {
        headers: { "content-type": "application/json" },
      }),
    ),
  );
  vi.stubGlobal("fetch", transport);
  await api.getPromptDiff("version", "historical");
  expect(
    new URL((transport.mock.calls[0][0] as Request).url).searchParams.get("base_version_id"),
  ).toBe("historical");
  const controller = new AbortController();
  await api.getPromptVersion("version", controller.signal);
  controller.abort();
  expect((transport.mock.calls[1][0] as Request).signal.aborted).toBe(true);
});

it("回滚发送历史目标和当前基准；预览变量不写浏览器存储", async () => {
  const local = vi.spyOn(Storage.prototype, "setItem");
  const transport = vi.fn().mockImplementation(() =>
    Promise.resolve(
      new Response(JSON.stringify({ code: 200, message: "ok", data: {} }), {
        headers: { "content-type": "application/json" },
      }),
    ),
  );
  vi.stubGlobal("fetch", transport);
  const body: api.RollbackRequest = {
    expected_active_version_id: "active",
    target_version_id: "historical",
    reason: "合成回滚原因",
  };
  await api.rollbackPromptDefinition("definition", body);
  expect(JSON.parse(await (transport.mock.calls[0][0] as Request).clone().text())).toEqual(body);
  await api.previewPromptVersion("version", { variables: { request: { target_job: null } } });
  expect(local).not.toHaveBeenCalled();
});
