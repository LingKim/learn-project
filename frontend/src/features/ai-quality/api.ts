import { authenticatedAccessToken } from "@/features/auth/auth-provider";
import {
  qualityCaseList,
  qualityCaseDetail,
  qualityAdminOverview,
  qualityAdminQueue,
  qualityAdminDetail,
  qualityAdminSnapshot,
  qualityCaseCreate,
  qualityCaseMessage,
  qualityGrantDecision,
  qualityGrantRevoke,
  qualityCaseWithdraw,
  qualityCaseClose,
  qualityAdminAssign,
  qualityAdminAccessRequest,
  qualityAdminReplay,
  qualityAdminMessage,
  qualityAdminTransition,
} from "@/lib/api/generated/sdk.gen";
import type {
  AccessRequest,
  AdminCaseDetail,
  AdminMessageCreate,
  AssignmentRequest,
  CaseCreate,
  CaseView,
  GrantDecision,
  GrantRevoke,
  MessageCreate,
  QualityAdminQueueData,
  QualityAdminSnapshotData,
  QualityCaseListData,
  QualityOverview,
  ReplayRequest,
  SnapshotView,
  TransitionRequest,
  UserCaseDetail,
  VersionRequest,
} from "@/lib/api/generated/types.gen";
import {
  API_BASE_URL,
  requestQueryData,
  requestPageData,
  requestMutation,
} from "@/lib/api/protocol";
export type {
  AccessRequest,
  AdminCaseDetail,
  AdminMessageCreate,
  AssignmentRequest,
  CaseCreate,
  CaseView,
  GrantDecision,
  GrantRevoke,
  MessageCreate,
  QualityAdminQueueData,
  QualityAdminSnapshotData,
  QualityCaseListData,
  QualityOverview,
  ReplayRequest,
  SnapshotView,
  TransitionRequest,
  UserCaseDetail,
  VersionRequest,
  GrantView,
  EventView,
  ReplayView,
} from "@/lib/api/generated/types.gen";

// 诊断正文只能经过当前会话的鉴权请求进入内存，不允许浏览器 HTTP 缓存保留副本。
async function options(signal?: AbortSignal) {
  return {
    baseUrl: API_BASE_URL,
    credentials: "include" as const,
    throwOnError: true as const,
    cache: "no-store" as const,
    signal,
    headers: { Authorization: `Bearer ${await authenticatedAccessToken()}` },
  };
}

export async function listCases(query: QualityCaseListData["query"] = {}, signal?: AbortSignal) {
  const auth = await options(signal);
  return requestPageData<CaseView>(() => qualityCaseList({ ...auth, query }));
}

export async function getCase(id: string, signal?: AbortSignal) {
  const auth = await options(signal);
  return requestQueryData<UserCaseDetail>(() =>
    qualityCaseDetail({ ...auth, path: { case_id: id } }),
  );
}

export async function getOverview(signal?: AbortSignal) {
  const auth = await options(signal);
  return requestQueryData<QualityOverview>(() => qualityAdminOverview({ ...auth }));
}

export async function listAdminCases(
  query: QualityAdminQueueData["query"] = {},
  signal?: AbortSignal,
) {
  const auth = await options(signal);
  return requestPageData<CaseView>(() => qualityAdminQueue({ ...auth, query }));
}

export async function getAdminCase(id: string, signal?: AbortSignal) {
  const auth = await options(signal);
  return requestQueryData<AdminCaseDetail>(() =>
    qualityAdminDetail({ ...auth, path: { case_id: id } }),
  );
}

export async function getSnapshot(
  id: string,
  query: QualityAdminSnapshotData["query"],
  signal?: AbortSignal,
) {
  const auth = await options(signal);
  return requestQueryData<SnapshotView>(() =>
    qualityAdminSnapshot({ ...auth, path: { case_id: id }, query }),
  );
}

export async function createCase(body: CaseCreate) {
  const auth = await options();
  return requestMutation<UserCaseDetail>(() => qualityCaseCreate({ ...auth, body }));
}

export async function addMessage(id: string, body: MessageCreate) {
  const auth = await options();
  return requestMutation<UserCaseDetail>(() =>
    qualityCaseMessage({ ...auth, path: { case_id: id }, body }),
  );
}

export async function decideGrant(id: string, grantId: string, body: GrantDecision) {
  const auth = await options();
  return requestMutation<UserCaseDetail>(() =>
    qualityGrantDecision({ ...auth, path: { case_id: id, grant_id: grantId }, body }),
  );
}

export async function revokeGrant(id: string, grantId: string, body: GrantRevoke) {
  const auth = await options();
  return requestMutation<UserCaseDetail>(() =>
    qualityGrantRevoke({ ...auth, path: { case_id: id, grant_id: grantId }, body }),
  );
}

export async function withdrawCase(id: string, body: VersionRequest) {
  const auth = await options();
  return requestMutation<UserCaseDetail>(() =>
    qualityCaseWithdraw({ ...auth, path: { case_id: id }, body }),
  );
}

export async function closeCase(id: string, body: VersionRequest) {
  const auth = await options();
  return requestMutation<UserCaseDetail>(() =>
    qualityCaseClose({ ...auth, path: { case_id: id }, body }),
  );
}

export async function assignCase(id: string, body: AssignmentRequest) {
  const auth = await options();
  return requestMutation<AdminCaseDetail>(() =>
    qualityAdminAssign({ ...auth, path: { case_id: id }, body }),
  );
}

export async function requestAccess(id: string, body: AccessRequest) {
  const auth = await options();
  return requestMutation<AdminCaseDetail>(() =>
    qualityAdminAccessRequest({ ...auth, path: { case_id: id }, body }),
  );
}

export async function replayCase(id: string, body: ReplayRequest) {
  const auth = await options();
  return requestMutation<AdminCaseDetail>(() =>
    qualityAdminReplay({ ...auth, path: { case_id: id }, body }),
  );
}

export async function addAdminMessage(id: string, body: AdminMessageCreate) {
  const auth = await options();
  return requestMutation<AdminCaseDetail>(() =>
    qualityAdminMessage({ ...auth, path: { case_id: id }, body }),
  );
}

export async function transitionCase(id: string, body: TransitionRequest) {
  const auth = await options();
  return requestMutation<AdminCaseDetail>(() =>
    qualityAdminTransition({ ...auth, path: { case_id: id }, body }),
  );
}
