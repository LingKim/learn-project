import { mutationOptions, queryOptions, type QueryClient } from "@tanstack/react-query";
import * as api from "./api";

export const promptManagementKeys = {
  all: ["prompt-management"] as const,
  lists: () => [...promptManagementKeys.all, "definitions", "list"] as const,
  list: (filters: api.DefinitionFilters) => [...promptManagementKeys.lists(), filters] as const,
  definition: (id: string) => [...promptManagementKeys.all, "definitions", id] as const,
  versions: (id: string, page: number) =>
    [...promptManagementKeys.definition(id), "versions", page] as const,
  version: (id: string) => [...promptManagementKeys.all, "versions", id] as const,
  detail: (id: string) => [...promptManagementKeys.version(id), "detail"] as const,
  diff: (id: string, baseVersionId?: string) =>
    [...promptManagementKeys.version(id), "diff", baseVersionId ?? null] as const,
  preview: (id: string) => [...promptManagementKeys.version(id), "preview"] as const,
  evaluation: (id: string) => [...promptManagementKeys.version(id), "evaluation"] as const,
  audit: (id: string, page: number) =>
    [...promptManagementKeys.definition(id), "audit", page] as const,
};

// 正文、Diff和预览只属于当前管理员会话；无人观察时立刻释放内存。
const privateQueryPolicy = { staleTime: 0, gcTime: 0, retry: false } as const;
export function promptDefinitionsOptions(filters: api.DefinitionFilters = {}, enabled = true) {
  return queryOptions({
    ...privateQueryPolicy,
    queryKey: promptManagementKeys.list(filters),
    queryFn: ({ signal }) => api.listPromptDefinitions(filters, signal),
    enabled,
  });
}
export function promptDefinitionOptions(id: string, enabled = true) {
  return queryOptions({
    ...privateQueryPolicy,
    queryKey: promptManagementKeys.definition(id),
    queryFn: ({ signal }) => api.getPromptDefinition(id, signal),
    enabled: Boolean(id && enabled),
  });
}
export function promptVersionsOptions(id: string, page = 1, enabled = true) {
  return queryOptions({
    ...privateQueryPolicy,
    queryKey: promptManagementKeys.versions(id, page),
    queryFn: ({ signal }) => api.listPromptVersions(id, page, signal),
    enabled: Boolean(id && enabled),
  });
}
export function promptVersionOptions(id: string, enabled = true) {
  return queryOptions({
    ...privateQueryPolicy,
    queryKey: promptManagementKeys.detail(id),
    queryFn: ({ signal }) => api.getPromptVersion(id, signal),
    enabled: Boolean(id && enabled),
  });
}
export function promptDiffOptions(id: string, baseVersionId?: string, enabled = true) {
  return queryOptions({
    ...privateQueryPolicy,
    queryKey: promptManagementKeys.diff(id, baseVersionId),
    queryFn: ({ signal }) => api.getPromptDiff(id, baseVersionId, signal),
    enabled: Boolean(id && enabled),
  });
}
export function promptAuditOptions(id: string, page = 1, enabled = true) {
  return queryOptions({
    ...privateQueryPolicy,
    queryKey: promptManagementKeys.audit(id, page),
    queryFn: ({ signal }) => api.listPromptAuditEvents(id, page, signal),
    enabled: Boolean(id && enabled),
  });
}

function mutation<Input, Output>(
  client: QueryClient,
  key: readonly unknown[],
  fn: (input: Input) => Promise<Output>,
) {
  return mutationOptions({
    mutationKey: key,
    mutationFn: fn,
    gcTime: 0,
    retry: false,
    meta: { errorMode: "local" as const, successToast: false },
    // 只有成功才更新服务器快照。冲突不改变输入、基准版本或既有缓存。
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: promptManagementKeys.all });
    },
  });
}
export function createPromptDraftOptions(client: QueryClient, definitionId: string) {
  return mutation(
    client,
    [...promptManagementKeys.definition(definitionId), "create"],
    (body: api.DraftCreate) => api.createPromptDraft(definitionId, body),
  );
}
export function patchPromptDraftOptions(client: QueryClient, versionId: string) {
  return mutation(
    client,
    [...promptManagementKeys.version(versionId), "patch"],
    (body: api.DraftPatch) => api.patchPromptDraft(versionId, body),
  );
}
export function previewPromptOptions(client: QueryClient, versionId: string) {
  return mutation(client, promptManagementKeys.preview(versionId), (body: api.PreviewRequest) =>
    api.previewPromptVersion(versionId, body),
  );
}
export function evaluatePromptOptions(client: QueryClient, versionId: string) {
  return mutation(client, promptManagementKeys.evaluation(versionId), () =>
    api.evaluatePromptVersion(versionId),
  );
}
export function publishPromptOptions(client: QueryClient, versionId: string) {
  return mutation(
    client,
    [...promptManagementKeys.version(versionId), "publish"],
    (body: api.PublishRequest) => api.publishPromptVersion(versionId, body),
  );
}
export function rollbackPromptOptions(client: QueryClient, definitionId: string) {
  return mutation(
    client,
    [...promptManagementKeys.definition(definitionId), "rollback"],
    (body: api.RollbackRequest) => api.rollbackPromptDefinition(definitionId, body),
  );
}
export function promptStatusOptions(client: QueryClient, definitionId: string) {
  return mutation(
    client,
    [...promptManagementKeys.definition(definitionId), "status"],
    (body: api.StatusRequest) => api.setPromptDefinitionStatus(definitionId, body),
  );
}

/** 离开管理范围时调用：取消读取，清除含正文的Query/Mutation。不会取消已提交的业务写入。 */
export async function clearPromptManagementCache(client: QueryClient) {
  await client.cancelQueries({ queryKey: promptManagementKeys.all });
  client.removeQueries({ queryKey: promptManagementKeys.all });
  const cache = client.getMutationCache();
  for (const item of cache.findAll({ mutationKey: promptManagementKeys.all })) cache.remove(item);
}
