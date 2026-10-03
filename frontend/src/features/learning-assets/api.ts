import { authenticatedAccessToken } from "@/features/auth/auth-provider";
import {
  weaknessList,
  weaknessCreate,
  weaknessDetail,
  weaknessPatch,
  weaknessConfirm,
  weaknessIgnore,
  weaknessRevoke,
  weaknessMastery,
  weaknessDelete,
  weaknessReviews,
  explanationList,
  explanationCreate,
  explanationDetail,
  explanationCard,
  explanationSourcePreview,
  explanationRegenerate,
  explanationDelete,
  explanationReviews,
  knowledgeRunGet,
  knowledgeRunLookup,
  knowledgeRunCancel,
  knowledgeRunRetry,
} from "@/lib/api/generated/sdk.gen";
import type {
  WeaknessListData,
  WeaknessCreate,
  WeaknessView,
  WeaknessDetail,
  WeaknessPatch,
  ConfirmRequest,
  VersionRequest,
  MasteryRequest,
  ExplanationCreate,
  ExplanationRegenerate,
  ExplanationAccepted,
  ExplanationView,
  ExplanationDetail,
  KnowledgeCardView,
  KnowledgeRunView,
  LearningReviewView,
  RetryRequest,
  SourcePreview,
} from "@/lib/api/generated/types.gen";
import {
  API_BASE_URL,
  requestQueryData,
  requestPageData,
  requestMutation,
  requestNoContent,
} from "@/lib/api/protocol";
export type {
  WeaknessCreate,
  WeaknessView,
  WeaknessDetail,
  WeaknessPatch,
  ConfirmRequest,
  VersionRequest,
  MasteryRequest,
  ExplanationConfig,
  ExplanationCreate,
  ExplanationRegenerate,
  ExplanationAccepted,
  ExplanationView,
  ExplanationDetail,
  KnowledgeCardView,
  KnowledgeRunView,
  LearningReviewView,
  RetryRequest,
  SourcePreview,
  EvidenceView,
} from "@/lib/api/generated/types.gen";
export type WeaknessFilters = NonNullable<WeaknessListData["query"]>;

async function options() {
  const token = await authenticatedAccessToken();
  return {
    baseUrl: API_BASE_URL,
    credentials: "include" as const,
    cache: "no-store" as const,
    throwOnError: true as const,
    headers: { Authorization: `Bearer ${token}` },
  };
}
export async function listWeaknesses(query: WeaknessFilters = {}) {
  const opts = await options();
  return requestPageData<WeaknessView>(() =>
    weaknessList({ ...opts, query: { page_size: 20, ...query } }),
  );
}
export async function createWeakness(body: WeaknessCreate) {
  const opts = await options();
  return requestMutation<WeaknessView>(() => weaknessCreate({ ...opts, body }));
}
export async function getWeakness(id: string) {
  const opts = await options();
  return requestQueryData<WeaknessDetail>(() =>
    weaknessDetail({ ...opts, path: { object_id: id } }),
  );
}
export async function patchWeakness(id: string, body: WeaknessPatch) {
  const opts = await options();
  return requestMutation<WeaknessView>(() =>
    weaknessPatch({ ...opts, path: { object_id: id }, body }),
  );
}
export async function confirmWeakness(id: string, body: ConfirmRequest) {
  const opts = await options();
  return requestMutation<WeaknessView>(() =>
    weaknessConfirm({ ...opts, path: { object_id: id }, body }),
  );
}
export async function ignoreWeakness(id: string, body: VersionRequest) {
  const opts = await options();
  return requestMutation<WeaknessView>(() =>
    weaknessIgnore({ ...opts, path: { object_id: id }, body }),
  );
}
export async function revokeWeakness(id: string, body: VersionRequest) {
  const opts = await options();
  return requestMutation<WeaknessView>(() =>
    weaknessRevoke({ ...opts, path: { object_id: id }, body }),
  );
}
export async function setWeaknessMastery(id: string, body: MasteryRequest) {
  const opts = await options();
  return requestMutation<WeaknessView>(() =>
    weaknessMastery({ ...opts, path: { object_id: id }, body }),
  );
}
export async function deleteWeakness(id: string, version: number) {
  const opts = await options();
  return requestNoContent(
    () => weaknessDelete({ ...opts, path: { object_id: id }, body: { expected_version: version } }),
    "难点已删除",
  );
}
export async function getWeaknessReviews(id: string, page = 1) {
  const opts = await options();
  return requestPageData<LearningReviewView>(() =>
    weaknessReviews({ ...opts, path: { object_id: id }, query: { page, page_size: 20 } }),
  );
}
export async function listExplanations(page = 1) {
  const opts = await options();
  return requestPageData<ExplanationView>(() =>
    explanationList({ ...opts, query: { page, page_size: 20 } }),
  );
}
export async function createExplanation(body: ExplanationCreate) {
  const opts = await options();
  return requestMutation<ExplanationAccepted>(() => explanationCreate({ ...opts, body }));
}
export async function getExplanation(id: string) {
  const opts = await options();
  return requestQueryData<ExplanationDetail>(() =>
    explanationDetail({ ...opts, path: { object_id: id } }),
  );
}
export async function getExplanationCard(id: string, version: number) {
  const opts = await options();
  return requestQueryData<KnowledgeCardView>(() =>
    explanationCard({ ...opts, path: { object_id: id, version } }),
  );
}
export async function getExplanationSource(id: string, version: number, sourceId: string) {
  const opts = await options();
  return requestQueryData<SourcePreview>(() =>
    explanationSourcePreview({ ...opts, path: { object_id: id, version, source_id: sourceId } }),
  );
}
export async function regenerateExplanation(id: string, body: ExplanationRegenerate) {
  const opts = await options();
  return requestMutation<ExplanationAccepted>(() =>
    explanationRegenerate({ ...opts, path: { object_id: id }, body }),
  );
}
export async function deleteExplanation(id: string, version: number) {
  const opts = await options();
  return requestNoContent(
    () =>
      explanationDelete({ ...opts, path: { object_id: id }, body: { expected_version: version } }),
    "精讲已删除",
  );
}
export async function getExplanationReviews(id: string, page = 1) {
  const opts = await options();
  return requestPageData<LearningReviewView>(() =>
    explanationReviews({ ...opts, path: { object_id: id }, query: { page, page_size: 20 } }),
  );
}
export async function getKnowledgeRun(id: string) {
  const opts = await options();
  return requestQueryData<KnowledgeRunView>(() =>
    knowledgeRunGet({ ...opts, path: { run_id: id } }),
  );
}
export async function lookupKnowledgeRun(requestKey: string) {
  const opts = await options();
  return requestQueryData<KnowledgeRunView>(() =>
    knowledgeRunLookup({ ...opts, query: { request_key: requestKey } }),
  );
}
export async function cancelKnowledgeRun(id: string) {
  const opts = await options();
  return requestMutation<KnowledgeRunView>(() =>
    knowledgeRunCancel({ ...opts, path: { run_id: id } }),
  );
}
export async function retryKnowledgeRun(id: string, body: RetryRequest) {
  const opts = await options();
  return requestMutation<KnowledgeRunView>(() =>
    knowledgeRunRetry({ ...opts, path: { run_id: id }, body }),
  );
}
