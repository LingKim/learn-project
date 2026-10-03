import { MutationObserver, QueryClient, QueryObserver } from "@tanstack/react-query";
import { waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import * as api from "./api";
import {
  promptManagementKeys as keys,
  promptDefinitionsOptions,
  promptDefinitionOptions,
  promptVersionsOptions,
  promptVersionOptions,
  promptDiffOptions,
  promptAuditOptions,
  previewPromptOptions,
  evaluatePromptOptions,
  publishPromptOptions,
  rollbackPromptOptions,
  clearPromptManagementCache,
} from "./queries";

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
beforeEach(() => {
  client = new QueryClient();
  vi.clearAllMocks();
});
afterEach(() => client.clear());
const version = { content: "合成正文", revision: 3 } as api.VersionView;

it("版本、Diff基准、定义分页和审计key各自隔离；keys不含正文或合成变量", () => {
  expect(keys.detail("v1")).not.toEqual(keys.detail("v2"));
  expect(keys.diff("v1", "v2")).not.toEqual(keys.diff("v1", "v3"));
  expect(keys.versions("d1", 1)).not.toEqual(keys.versions("d1", 2));
  expect(keys.audit("d1", 1)).not.toEqual(keys.versions("d1", 1));
  expect(keys.preview("v1")).not.toEqual(keys.evaluation("v1"));
  expect(keys.list({ runtime_status: "enabled" })).not.toEqual(
    keys.list({ runtime_status: "disabled" }),
  );
});

it("所有读取零stale/零GC且可在管理员认证前禁用", () => {
  for (const options of [
    promptDefinitionsOptions({}, false),
    promptDefinitionOptions("d", false),
    promptVersionsOptions("d", 1, false),
    promptVersionOptions("v", false),
    promptDiffOptions("v", "base", false),
    promptAuditOptions("d", 1, false),
  ]) {
    expect(options).toMatchObject({ gcTime: 0, staleTime: 0, retry: false, enabled: false });
  }
  expect(promptVersionOptions("").enabled).toBe(false);
});

it("离开版本详情后无人观察即释放正文，重新打开另一个版本不复用旧正文", async () => {
  vi.mocked(api.getPromptVersion).mockResolvedValue(version);
  const observer = new QueryObserver(client, promptVersionOptions("v1"));
  const unsubscribe = observer.subscribe(() => undefined);
  await waitFor(() => expect(observer.getCurrentResult().isSuccess).toBe(true));
  expect(client.getQueryData(keys.detail("v1"))).toBe(version);
  expect(client.getQueryData(keys.detail("v2"))).toBeUndefined();
  unsubscribe();
  await waitFor(() => expect(client.getQueryData(keys.detail("v1"))).toBeUndefined());
});

it("取消读取后迟到响应不能恢复正文缓存；清理只移除本feature", async () => {
  let finish!: (value: api.VersionView) => void;
  let signal!: AbortSignal;
  vi.mocked(api.getPromptVersion).mockImplementation((_id, requestSignal) => {
    signal = requestSignal!;
    return new Promise((resolve) => {
      finish = resolve;
    });
  });
  client.setQueryData(["practice", "run"], { id: "unrelated" });
  const observer = new QueryObserver(client, promptVersionOptions("v1"));
  const unsubscribe = observer.subscribe(() => undefined);
  await waitFor(() => expect(api.getPromptVersion).toHaveBeenCalledTimes(1));
  await clearPromptManagementCache(client);
  expect(signal.aborted).toBe(true);
  finish(version);
  await Promise.resolve();
  expect(client.getQueryData(keys.detail("v1"))).toBeUndefined();
  expect(client.getQueryData(["practice", "run"])).toEqual({ id: "unrelated" });
  unsubscribe();
});

it.each(["publish", "rollback"] as const)(
  "%s遇409只执行一次，不改基准/输入或草稿缓存",
  async (action) => {
    const conflict = new ApiError("基准已更新", {
      status: 409,
      errorKey: "PROMPT_VERSION_CONFLICT",
    });
    vi.mocked(api.publishPromptVersion).mockRejectedValue(conflict);
    vi.mocked(api.rollbackPromptDefinition).mockRejectedValue(conflict);
    client.setQueryData(keys.detail("v1"), version);
    const invalidation = vi.spyOn(client, "invalidateQueries");
    const publishBody: api.PublishRequest = {
      expected_active_version_id: "active",
      expected_revision: 3,
    };
    const rollbackBody: api.RollbackRequest = {
      expected_active_version_id: "active",
      target_version_id: "historic",
      reason: "合成原因",
    };
    const before = JSON.stringify({ publishBody, rollbackBody });
    if (action === "publish") {
      const observer = new MutationObserver(client, publishPromptOptions(client, "v1"));
      await expect(observer.mutate(publishBody)).rejects.toBe(conflict);
      expect(api.publishPromptVersion).toHaveBeenCalledTimes(1);
    } else {
      const observer = new MutationObserver(client, rollbackPromptOptions(client, "d1"));
      await expect(observer.mutate(rollbackBody)).rejects.toBe(conflict);
      expect(api.rollbackPromptDefinition).toHaveBeenCalledTimes(1);
    }
    expect(invalidation).not.toHaveBeenCalled();
    expect(client.getQueryData(keys.detail("v1"))).toBe(version);
    expect(JSON.stringify({ publishBody, rollbackBody })).toBe(before);
  },
);

it("预览及评测仅显式mutation发起；预览正文和输入可随管理范围一起清理", async () => {
  vi.mocked(api.previewPromptVersion).mockResolvedValue({
    data: { system_messages: ["合成指令"] } as api.PreviewView,
    message: "ok",
  });
  const options = previewPromptOptions(client, "v1");
  expect(options).toMatchObject({
    retry: false,
    gcTime: 0,
    meta: { errorMode: "local", successToast: false },
  });
  expect(evaluatePromptOptions(client, "v1").retry).toBe(false);
  expect(api.previewPromptVersion).not.toHaveBeenCalled();
  expect(api.evaluatePromptVersion).not.toHaveBeenCalled();
  const observer = new MutationObserver(client, options);
  const unsubscribe = observer.subscribe(() => undefined);
  await observer.mutate({ variables: { request: { target_job: null } } });
  expect(client.getMutationCache().getAll()).toHaveLength(1);
  await clearPromptManagementCache(client);
  expect(client.getMutationCache().getAll()).toHaveLength(0);
  expect(api.evaluatePromptVersion).not.toHaveBeenCalled();
  unsubscribe();
});

it("范围清理的取消完成后，不删除下一页面已经建立的新缓存", async () => {
  client.setQueryData(keys.detail("old"), version);
  const removing = clearPromptManagementCache(client);
  client.setQueryData(keys.detail("new"), { id: "next-page" });
  await removing;
  expect(client.getQueryData(keys.detail("old"))).toBeUndefined();
  expect(client.getQueryData(keys.detail("new"))).toEqual({ id: "next-page" });
});
