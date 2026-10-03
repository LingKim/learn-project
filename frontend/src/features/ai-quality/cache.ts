import type { QueryClient, QueryKey } from "@tanstack/react-query";
import type { SnapshotView, UserCaseDetail, AdminCaseDetail } from "./api";

export const qualityKeys = {
  all: ["ai-quality"] as const,
  userLists: ["ai-quality", "user", "list"] as const,
  adminLists: ["ai-quality", "admin", "list"] as const,
  overview: ["ai-quality", "admin", "overview"] as const,
  detail: (role: "user" | "admin", id: string, version: number) =>
    ["ai-quality", role, "detail", id, version] as const,
  snapshot: (
    id: string,
    caseVersion: number,
    grantId: string,
    grantVersion: number,
    fields: string[],
  ) =>
    [
      "ai-quality",
      "admin",
      "snapshot",
      id,
      caseVersion,
      grantId,
      grantVersion,
      [...new Set(fields)].sort(),
    ] as const,
};

function bodyKey(key: QueryKey, id?: string) {
  return (
    key[0] === "ai-quality" &&
    ["snapshot", "detail"].includes(String(key[2])) &&
    (id === undefined || key[3] === id)
  );
}

// 撤销与版本变化先清除旧正文；取消中的 SDK 请求使用 signal，迟到响应不能重新填回旧缓存。
export async function removeQualityBody(client: QueryClient, id?: string) {
  const filters = { predicate: (query: { queryKey: QueryKey }) => bodyKey(query.queryKey, id) };
  const cancelled = client.cancelQueries(filters);
  for (const query of client.getQueryCache().findAll(filters)) {
    // active observer 仍可持有已移出 QueryCache 的对象，必须先通知它丢弃正文。
    query.setState({ data: undefined, dataUpdatedAt: 0, status: "pending" });
  }
  client.removeQueries(filters);
  await cancelled;
}

const installed = new WeakSet<QueryClient>();
export function protectQualityCache(client: QueryClient) {
  if (installed.has(client)) return;
  installed.add(client);
  const timers = new Map<string, ReturnType<typeof setTimeout>>();
  client.getQueryCache().subscribe((event) => {
    const query = event.query;
    if (!bodyKey(query.queryKey)) return;
    if (
      event.type !== "removed" &&
      event.type !== "added" &&
      !(event.type === "updated" && event.action.type === "success")
    )
      return;
    const previous = timers.get(query.queryHash);
    if (previous) clearTimeout(previous);
    timers.delete(query.queryHash);
    if (event.type === "removed" || !query.state.data) return;
    let expiry: number | undefined;
    if (query.queryKey[2] === "snapshot") {
      expiry = Date.parse((query.state.data as SnapshotView).expires_at);
    } else {
      const detail = query.state.data as UserCaseDetail | AdminCaseDetail;
      const basic = detail.grants.find((grant) => grant.fields.includes("query"));
      const hasBody =
        ("description" in detail && detail.description != null) ||
        detail.events.some((item) => item.content != null);
      if (basic?.status === "active") expiry = Date.parse(basic.expires_at);
      else if (hasBody) expiry = Date.now();
      if (detail.status === "closed") expiry = hasBody ? Date.now() : undefined;
    }
    if (expiry === undefined) return;
    // 最长授权 30 天超过单次浏览器 timer 上限；分段等待仍以服务端 expiry 为准。
    const expire = () => {
      const remaining = expiry! - Date.now();
      if (Number.isFinite(remaining) && remaining > 0) {
        timers.set(query.queryHash, setTimeout(expire, Math.min(remaining, 2_147_483_647)));
      } else {
        timers.delete(query.queryHash);
        void removeQualityBody(client, String(query.queryKey[3]));
      }
    };
    expire();
  });
}
