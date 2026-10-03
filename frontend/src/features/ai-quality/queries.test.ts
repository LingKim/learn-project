import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryObserver } from "@tanstack/react-query";
import * as api from "./api";
import {
  qualityKeys,
  protectQualityCache,
  removeQualityBody,
  snapshotQueryOptions,
  revokeGrantMutationOptions,
  caseQueryOptions,
  adminCaseQueryOptions,
} from "./queries";
import type { GrantView, SnapshotView, UserCaseDetail } from "./api";
vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  getSnapshot: vi.fn(),
  revokeGrant: vi.fn(),
}));
afterEach(() => vi.useRealTimers());
const grant: GrantView = {
  id: "grant",
  version: 2,
  status: "active",
  fields: ["query"],
  chunk_ids: [],
  reason: "诊断",
  requester_id: null,
  expires_at: "2026-10-03T00:00:10Z",
  confirmed_at: null,
  revoked_at: null,
};
const detail: UserCaseDetail = {
  id: "case",
  case_number: "Q-1",
  user_id: "owner",
  source_type: "learning_turn",
  source_id: "turn",
  trace_id: "trace",
  category: "wrong_answer",
  status: "submitted",
  version: 3,
  strategy_version: "fts-v1",
  assignee_id: null,
  created_at: "2026-10-03T00:00:00Z",
  updated_at: "2026-10-03T00:00:00Z",
  resolved_at: null,
  closed_at: null,
  resolution_code: null,
  resolution_summary: null,
  description: "私有描述",
  expected_result: null,
  grants: [grant],
  events: [],
};
const snapshot: SnapshotView = {
  case_id: "case",
  grant_id: "grant",
  grant_version: 2,
  expires_at: grant.expires_at,
  values: { query: "私有问题" },
  description: "私有描述",
  expected_result: null,
};
function setup() {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-03T00:00:00Z"));
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  protectQualityCache(client);
  return client;
}
describe("质量正文缓存边界", () => {
  it("区分角色、工单版本、grant版本与fields，字段顺序不改变同一范围", () => {
    const client = setup();
    const input = {
      grant_id: "grant",
      expected_grant_version: 2,
      fields: ["query", "final_output"] as ("query" | "final_output")[],
    };
    const a = snapshotQueryOptions(client, "case", 3, input);
    expect(a.queryKey).toEqual(
      snapshotQueryOptions(client, "case", 3, { ...input, fields: [...input.fields].reverse() })
        .queryKey,
    );
    expect(a.queryKey).not.toEqual(snapshotQueryOptions(client, "case", 4, input).queryKey);
    expect(a.queryKey).not.toEqual(
      snapshotQueryOptions(client, "case", 3, { ...input, expected_grant_version: 3 }).queryKey,
    );
    expect(a.queryKey).not.toEqual(
      snapshotQueryOptions(client, "case", 3, { ...input, fields: ["query"] }).queryKey,
    );
    expect(caseQueryOptions(client, "case", 3).queryKey).not.toEqual(
      adminCaseQueryOptions(client, "case", 3).queryKey,
    );
    expect(a).toMatchObject({ gcTime: 0, staleTime: 0, retry: false });
    client.clear();
  });
  it("grant到期立即删除snapshot和含描述的详情，但保留无正文列表", async () => {
    const client = setup();
    const key = qualityKeys.snapshot("case", 3, "grant", 2, ["query"]);
    client.setQueryData(qualityKeys.userLists, { data: [] });
    client.setQueryData(qualityKeys.detail("user", "case", 3), detail);
    client.setQueryData(key, snapshot);
    expect(client.getQueryData(key)).toEqual(snapshot);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(client.getQueryData(key)).toBeUndefined();
    expect(client.getQueryData(qualityKeys.detail("user", "case", 3))).toBeUndefined();
    expect(client.getQueryData(qualityKeys.userLists)).toEqual({ data: [] });
    client.clear();
  });
  it("关闭或已撤销的返回值不保留诊断描述", async () => {
    const client = setup();
    const key = qualityKeys.detail("user", "case", 3);
    client.setQueryData(key, {
      ...detail,
      grants: [{ ...grant, status: "revoked" }],
    } satisfies UserCaseDetail);
    await Promise.resolve();
    await Promise.resolve();
    expect(client.getQueryData(key)).toBeUndefined();
    client.clear();
  });
  it("撤销开始就清除旧正文，并取消挂起的读取；迟到响应不能回填", async () => {
    const client = setup();
    let complete!: (value: SnapshotView) => void;
    let signal: AbortSignal | undefined;
    vi.mocked(api.getSnapshot).mockImplementation((_id, _query, current) => {
      signal = current;
      return new Promise((resolve) => {
        complete = resolve;
      });
    });
    const options = snapshotQueryOptions(client, "case", 3, {
      grant_id: "grant",
      expected_grant_version: 2,
      fields: ["query"],
    });
    const pending = client.fetchQuery(options).catch(() => undefined);
    const revoke = revokeGrantMutationOptions(client);
    await revoke.onMutate!(
      { id: "case", grantId: "grant", body: { expected_version: 3, expected_grant_version: 2 } },
      {} as never,
    );
    expect(signal?.aborted).toBe(true);
    complete(snapshot);
    await pending;
    expect(client.getQueryData(options.queryKey)).toBeUndefined();
    client.clear();
  });
  it("授权过期同时清除活跃 observer 持有的正文", async () => {
    const client = setup();
    const options = snapshotQueryOptions(client, "case", 3, {
      grant_id: "grant",
      expected_grant_version: 2,
      fields: ["query"],
    });
    const observer = new QueryObserver(client, {
      ...options,
      initialData: snapshot,
      enabled: false,
    });
    const unsubscribe = observer.subscribe(() => {});
    expect(observer.getCurrentResult().data).toEqual(snapshot);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(observer.getCurrentResult().data).toBeUndefined();
    unsubscribe();
    client.clear();
  });
  it("30天expiry不会因为浏览器timer上限而提前清空；会话清理取消调度", async () => {
    const client = setup();
    const expiry = new Date(Date.now() + 30 * 86400_000).toISOString();
    const key = qualityKeys.snapshot("case", 3, "grant", 2, ["query"]);
    client.setQueryData(key, { ...snapshot, expires_at: expiry });
    await vi.advanceTimersByTimeAsync(2_147_483_647);
    expect(client.getQueryData(key)).toBeDefined();
    await vi.advanceTimersByTimeAsync(30 * 86400_000 - 2_147_483_647);
    expect(client.getQueryData(key)).toBeUndefined();
    client.clear();
    expect(vi.getTimerCount()).toBe(0);
  });
  it("清理当前case不删除其他case或元数据", async () => {
    const client = setup();
    const other = qualityKeys.snapshot("other", 1, "other-grant", 1, ["query"]);
    client.setQueryData(other, { ...snapshot, case_id: "other" });
    client.setQueryData(qualityKeys.detail("user", "case", 3), detail);
    await removeQualityBody(client, "case");
    expect(client.getQueryData(other)).toBeDefined();
    client.clear();
  });
});
