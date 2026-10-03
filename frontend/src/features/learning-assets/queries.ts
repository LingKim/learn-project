import { mutationOptions, queryOptions, type QueryClient } from "@tanstack/react-query";
import * as api from "./api";
import { userProfileKeys } from "@/features/user-profile/queries";
export const learningAssetKeys = {
  all: ["learning-assets"] as const,
  weaknesses: () => ["learning-assets", "weaknesses"] as const,
  weaknessLists: () => ["learning-assets", "weaknesses", "list"] as const,
  weaknessList: (filters: api.WeaknessFilters) =>
    ["learning-assets", "weaknesses", "list", filters] as const,
  weakness: (id: string) => ["learning-assets", "weaknesses", id] as const,
  explanations: () => ["learning-assets", "explanations"] as const,
  explanationLists: () => ["learning-assets", "explanations", "list"] as const,
  explanationList: (page: number) => ["learning-assets", "explanations", "list", page] as const,
  explanation: (id: string) => ["learning-assets", "explanations", id] as const,
  card: (id: string, version: number) =>
    ["learning-assets", "explanations", id, "card", version] as const,
  sources: (id: string, version: number) =>
    ["learning-assets", "explanations", id, "card", version, "source"] as const,
  source: (id: string, version: number, sourceId: string) =>
    ["learning-assets", "explanations", id, "card", version, "source", sourceId] as const,
  run: (id: string) => ["learning-assets", "runs", id] as const,
  lookup: (key: string) => ["learning-assets", "lookup", key] as const,
};
export function activeKnowledgeRun(run: api.KnowledgeRunView | null | undefined) {
  return Boolean(run && ["pending", "processing", "cancel_requested"].includes(run.status));
}
export function weaknessListOptions(filters: api.WeaknessFilters = {}) {
  return queryOptions({
    queryKey: learningAssetKeys.weaknessList(filters),
    queryFn: () => api.listWeaknesses(filters),
    staleTime: 0,
  });
}
export function weaknessOptions(id: string) {
  return queryOptions({
    queryKey: learningAssetKeys.weakness(id),
    queryFn: () => api.getWeakness(id),
    enabled: Boolean(id),
    staleTime: 0,
    refetchInterval: (query) => (activeKnowledgeRun(query.state.data?.run) ? 2000 : false),
  });
}
export function explanationListOptions(page = 1) {
  return queryOptions({
    queryKey: learningAssetKeys.explanationList(page),
    queryFn: () => api.listExplanations(page),
    staleTime: 0,
  });
}
export function explanationOptions(id: string) {
  return queryOptions({
    queryKey: learningAssetKeys.explanation(id),
    queryFn: () => api.getExplanation(id),
    enabled: Boolean(id),
    staleTime: 0,
    refetchInterval: (query) => (activeKnowledgeRun(query.state.data?.run) ? 2000 : false),
  });
}
export function explanationCardOptions(id: string, version: number) {
  return queryOptions({
    queryKey: learningAssetKeys.card(id, version),
    queryFn: () => api.getExplanationCard(id, version),
    enabled: Boolean(id && version),
    staleTime: 0,
  });
}
export function explanationSourceOptions(id: string, version: number, sourceId: string) {
  return queryOptions({
    queryKey: learningAssetKeys.source(id, version, sourceId),
    queryFn: () => api.getExplanationSource(id, version, sourceId),
    enabled: Boolean(id && version && sourceId),
    staleTime: 0,
    retry: false,
  });
}
export function knowledgeRunOptions(id: string) {
  return queryOptions({
    queryKey: learningAssetKeys.run(id),
    queryFn: () => api.getKnowledgeRun(id),
    enabled: Boolean(id),
    staleTime: 0,
    refetchInterval: (query) => (activeKnowledgeRun(query.state.data) ? 2000 : false),
  });
}
export function knowledgeLookupOptions(key: string) {
  return queryOptions({
    queryKey: learningAssetKeys.lookup(key),
    queryFn: () => api.lookupKnowledgeRun(key),
    enabled: Boolean(key),
    staleTime: 0,
    retry: false,
  });
}
export function weaknessReviewOptions(id: string, page = 1) {
  return queryOptions({
    queryKey: [...learningAssetKeys.weakness(id), "reviews", page],
    queryFn: () => api.getWeaknessReviews(id, page),
    enabled: Boolean(id),
    staleTime: 0,
  });
}
export function explanationReviewOptions(id: string, page = 1) {
  return queryOptions({
    queryKey: [...learningAssetKeys.explanation(id), "reviews", page],
    queryFn: () => api.getExplanationReviews(id, page),
    enabled: Boolean(id),
    staleTime: 0,
  });
}
function mutation<Input, Output>(name: string, fn: (input: Input) => Promise<Output>) {
  return mutationOptions({
    mutationKey: [...learningAssetKeys.all, name],
    mutationFn: fn,
    retry: false,
    meta: { errorMode: "local" as const, successToast: false },
  });
}
export function createWeaknessOptions() {
  return mutation("create-weakness", api.createWeakness);
}
export function patchWeaknessOptions() {
  return mutation("patch-weakness", ({ id, body }: { id: string; body: api.WeaknessPatch }) =>
    api.patchWeakness(id, body),
  );
}
export function confirmWeaknessOptions() {
  return mutation("confirm-weakness", ({ id, body }: { id: string; body: api.ConfirmRequest }) =>
    api.confirmWeakness(id, body),
  );
}
export function ignoreWeaknessOptions() {
  return mutation("ignore-weakness", ({ id, body }: { id: string; body: api.VersionRequest }) =>
    api.ignoreWeakness(id, body),
  );
}
export function revokeWeaknessOptions() {
  return mutation("revoke-weakness", ({ id, body }: { id: string; body: api.VersionRequest }) =>
    api.revokeWeakness(id, body),
  );
}
export function masteryWeaknessOptions() {
  return mutation("mastery-weakness", ({ id, body }: { id: string; body: api.MasteryRequest }) =>
    api.setWeaknessMastery(id, body),
  );
}
export function deleteWeaknessOptions(client: QueryClient) {
  return mutationOptions({
    ...mutation("delete-weakness", ({ id, version }: { id: string; version: number }) =>
      api.deleteWeakness(id, version),
    ),
    onSuccess: async (_result, input) => {
      const detail = client.getQueryData<api.WeaknessDetail>(learningAssetKeys.weakness(input.id));
      if (detail?.explanation_id)
        client.removeQueries({ queryKey: learningAssetKeys.explanation(detail.explanation_id) });
      client.removeQueries({ queryKey: learningAssetKeys.weakness(input.id) });
      await Promise.all([
        client.invalidateQueries({ queryKey: learningAssetKeys.weaknessLists() }),
        client.invalidateQueries({ queryKey: userProfileKeys.detail() }),
      ]);
    },
  });
}
export function createExplanationOptions() {
  return mutation("create-explanation", api.createExplanation);
}
export function regenerateExplanationOptions() {
  return mutation(
    "regenerate-explanation",
    ({ id, body }: { id: string; body: api.ExplanationRegenerate }) =>
      api.regenerateExplanation(id, body),
  );
}
export function deleteExplanationOptions(client: QueryClient) {
  return mutationOptions({
    ...mutation("delete-explanation", ({ id, version }: { id: string; version: number }) =>
      api.deleteExplanation(id, version),
    ),
    onSuccess: async (_result, input) => {
      client.removeQueries({ queryKey: learningAssetKeys.explanation(input.id) });
      await client.invalidateQueries({ queryKey: learningAssetKeys.explanationLists() });
    },
  });
}
export function cancelKnowledgeOptions() {
  return mutation("cancel-knowledge", api.cancelKnowledgeRun);
}
export function retryKnowledgeOptions() {
  return mutation("retry-knowledge", ({ id, body }: { id: string; body: api.RetryRequest }) =>
    api.retryKnowledgeRun(id, body),
  );
}
