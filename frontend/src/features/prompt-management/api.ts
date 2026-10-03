import { authenticatedAccessToken } from "@/features/auth/auth-provider";
import {
  promptDefinitionsList,
  promptDefinitionGet,
  promptVersionsList,
  promptDraftCreate,
  promptVersionGet,
  promptDraftPatch,
  promptVersionDiff,
  promptVersionPreview,
  promptEvaluationRun,
  promptVersionPublish,
  promptDefinitionRollback,
  promptDefinitionStatus,
  promptAuditList,
} from "@/lib/api/generated/sdk.gen";
import type {
  DefinitionView,
  VersionSummary,
  VersionView,
  DraftCreate,
  DraftPatch,
  DiffView,
  PreviewRequest,
  PreviewView,
  EvaluationView,
  PublishRequest,
  RollbackRequest,
  StatusRequest,
  PromptDefinitionsListData,
  XuemianAiPromptManagementSchemasAuditView as AuditView,
} from "@/lib/api/generated/types.gen";
import {
  API_BASE_URL,
  requestPageData,
  requestQueryData,
  requestMutation,
} from "@/lib/api/protocol";

export type {
  DefinitionView,
  VersionSummary,
  VersionView,
  DraftCreate,
  DraftPatch,
  DiffView,
  PreviewRequest,
  PreviewView,
  EvaluationView,
  PublishRequest,
  RollbackRequest,
  StatusRequest,
  AuditView,
};
export type { Variable, DependencyInput, DependencyView } from "@/lib/api/generated/types.gen";
export type DefinitionFilters = NonNullable<PromptDefinitionsListData["query"]>;

/** 正文只在管理员当前操作中使用；读取和写入都禁止 HTTP 缓存。 */
async function options(signal?: AbortSignal) {
  const token = await authenticatedAccessToken();
  return {
    baseUrl: API_BASE_URL,
    credentials: "include" as const,
    cache: "no-store" as const,
    throwOnError: true as const,
    signal,
    headers: { Authorization: `Bearer ${token}` },
  };
}

export async function listPromptDefinitions(filters: DefinitionFilters = {}, signal?: AbortSignal) {
  const opts = await options(signal);
  return requestPageData<DefinitionView>(() =>
    promptDefinitionsList({ ...opts, query: { page: 1, page_size: 20, ...filters } }),
  );
}
export async function getPromptDefinition(id: string, signal?: AbortSignal) {
  const opts = await options(signal);
  return requestQueryData<DefinitionView>(() =>
    promptDefinitionGet({ ...opts, path: { definition_id: id } }),
  );
}
export async function listPromptVersions(id: string, page = 1, signal?: AbortSignal) {
  const opts = await options(signal);
  return requestPageData<VersionSummary>(() =>
    promptVersionsList({ ...opts, path: { definition_id: id }, query: { page, page_size: 20 } }),
  );
}
export async function getPromptVersion(id: string, signal?: AbortSignal) {
  const opts = await options(signal);
  return requestQueryData<VersionView>(() =>
    promptVersionGet({ ...opts, path: { version_id: id } }),
  );
}
export async function getPromptDiff(id: string, baseVersionId?: string, signal?: AbortSignal) {
  const opts = await options(signal);
  return requestQueryData<DiffView>(() =>
    promptVersionDiff({
      ...opts,
      path: { version_id: id },
      query: { base_version_id: baseVersionId },
    }),
  );
}
export async function listPromptAuditEvents(id: string, page = 1, signal?: AbortSignal) {
  const opts = await options(signal);
  return requestPageData<AuditView>(() =>
    promptAuditList({ ...opts, path: { definition_id: id }, query: { page, page_size: 20 } }),
  );
}
export async function createPromptDraft(id: string, body: DraftCreate) {
  const opts = await options();
  return requestMutation<VersionView>(() =>
    promptDraftCreate({ ...opts, path: { definition_id: id }, body }),
  );
}
export async function patchPromptDraft(id: string, body: DraftPatch) {
  const opts = await options();
  return requestMutation<VersionView>(() =>
    promptDraftPatch({ ...opts, path: { version_id: id }, body }),
  );
}
export async function previewPromptVersion(id: string, body: PreviewRequest) {
  const opts = await options();
  return requestMutation<PreviewView>(() =>
    promptVersionPreview({ ...opts, path: { version_id: id }, body }),
  );
}
export async function evaluatePromptVersion(id: string) {
  const opts = await options();
  return requestMutation<EvaluationView>(() =>
    promptEvaluationRun({ ...opts, path: { version_id: id } }),
  );
}
export async function publishPromptVersion(id: string, body: PublishRequest) {
  const opts = await options();
  return requestMutation<VersionView>(() =>
    promptVersionPublish({ ...opts, path: { version_id: id }, body }),
  );
}
export async function rollbackPromptDefinition(id: string, body: RollbackRequest) {
  const opts = await options();
  return requestMutation<VersionView>(() =>
    promptDefinitionRollback({ ...opts, path: { definition_id: id }, body }),
  );
}
export async function setPromptDefinitionStatus(id: string, body: StatusRequest) {
  const opts = await options();
  return requestMutation<DefinitionView>(() =>
    promptDefinitionStatus({ ...opts, path: { definition_id: id }, body }),
  );
}
