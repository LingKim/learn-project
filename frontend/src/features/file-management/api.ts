import {
  fileUploadSessionsCancel,
  fileUploadSessionsComplete,
  fileUploadSessionsCreate,
  fileUploadSessionsGet,
  fileUploadSessionsRenew,
  fileUploadSessionsResolveDuplicate,
  fileUploadSessionsSignParts,
  knowledgeBaseFilesDelete,
  knowledgeBaseFilesDeletionImpact,
  knowledgeBaseFilesDownloadUrl,
  knowledgeBaseFilesList,
  knowledgeBaseFilesMove,
  knowledgeBaseFilesUpdate,
  knowledgeBasesCreate,
  knowledgeBasesDelete,
  knowledgeBasesDeletionImpact,
  knowledgeBasesList,
  knowledgeBasesUpdate,
} from "@/lib/api/generated/sdk.gen";
import type {
  CompleteUploadRequest,
  DeleteRequest,
  DeleteResult,
  DeletionImpactView,
  DownloadUrlView,
  DuplicateResolutionRequest,
  KnowledgeBaseCreate,
  KnowledgeBaseUpdate,
  KnowledgeBaseView,
  KnowledgeFileMove,
  KnowledgeFileUpdate,
  KnowledgeFileView,
  SignedPart,
  SignPartsRequest,
  UploadPlan,
  UploadSessionCreate,
  UploadSessionView,
} from "@/lib/api/generated/types.gen";
import {
  API_BASE_URL,
  requestMutation,
  requestPageData,
  requestQueryData,
  type MutationResult,
  type PageData,
} from "@/lib/api/protocol";
import { authenticatedAccessToken } from "@/features/auth/auth-provider";
import { putPresignedObject } from "@/lib/api/upload-transport";

const sharedOptions = {
  baseUrl: API_BASE_URL,
  credentials: "include" as const,
  throwOnError: true as const,
};

async function authorizedOptions() {
  const accessToken = await authenticatedAccessToken();
  return {
    ...sharedOptions,
    headers: { Authorization: `Bearer ${accessToken}` },
  };
}

export type {
  DeleteRequest,
  DeleteResult,
  DeletionImpactView,
  DownloadUrlView,
  KnowledgeBaseCreate,
  KnowledgeBaseUpdate,
  KnowledgeBaseView,
  KnowledgeFileMove,
  KnowledgeFileUpdate,
  KnowledgeFileView,
  UploadPlan,
  UploadSessionView,
};

export type KnowledgeBaseListInput = { page?: number; pageSize?: number };
export type KnowledgeFileListInput = {
  knowledgeBaseId: string;
  page?: number;
  pageSize?: number;
  search?: string;
  status?: string;
};

export async function listKnowledgeBases({
  page = 1,
  pageSize = 20,
}: KnowledgeBaseListInput = {}): Promise<PageData<KnowledgeBaseView>> {
  const options = await authorizedOptions();
  return requestPageData(() =>
    knowledgeBasesList({ ...options, query: { page, page_size: pageSize } }),
  );
}

export async function createKnowledgeBase(
  body: KnowledgeBaseCreate,
): Promise<MutationResult<KnowledgeBaseView>> {
  const options = await authorizedOptions();
  return requestMutation(() => knowledgeBasesCreate({ ...options, body }));
}

export async function updateKnowledgeBase(
  knowledgeBaseId: string,
  body: KnowledgeBaseUpdate,
): Promise<MutationResult<KnowledgeBaseView>> {
  const options = await authorizedOptions();
  return requestMutation(() =>
    knowledgeBasesUpdate({
      ...options,
      path: { knowledge_base_id: knowledgeBaseId },
      body,
    }),
  );
}

export async function getKnowledgeBaseDeletionImpact(
  knowledgeBaseId: string,
  mode: DeleteRequest["mode"] = "SOURCE_ONLY",
): Promise<DeletionImpactView> {
  const options = await authorizedOptions();
  return requestQueryData(() =>
    knowledgeBasesDeletionImpact({
      ...options,
      path: { knowledge_base_id: knowledgeBaseId },
      query: { mode },
    }),
  );
}

export async function deleteKnowledgeBase(
  knowledgeBaseId: string,
  body: DeleteRequest,
): Promise<MutationResult<DeleteResult>> {
  const options = await authorizedOptions();
  return requestMutation(() =>
    knowledgeBasesDelete({
      ...options,
      path: { knowledge_base_id: knowledgeBaseId },
      body,
    }),
  );
}

export async function createUploadSession(
  knowledgeBaseId: string,
  body: UploadSessionCreate,
  idempotencyKey: string,
): Promise<MutationResult<UploadPlan>> {
  const options = await authorizedOptions();
  return requestMutation(() =>
    fileUploadSessionsCreate({
      ...options,
      headers: { ...options.headers, "Idempotency-Key": idempotencyKey },
      path: { knowledge_base_id: knowledgeBaseId },
      body,
    }),
  );
}

export async function signUploadParts(
  sessionId: string,
  body: SignPartsRequest,
): Promise<MutationResult<SignedPart[]>> {
  const options = await authorizedOptions();
  return requestMutation(() =>
    fileUploadSessionsSignParts({ ...options, path: { session_id: sessionId }, body }),
  );
}

export async function renewUploadPlan(sessionId: string): Promise<MutationResult<UploadPlan>> {
  const options = await authorizedOptions();
  return requestMutation(() =>
    fileUploadSessionsRenew({ ...options, path: { session_id: sessionId } }),
  );
}

export async function completeUploadSession(
  sessionId: string,
  body: CompleteUploadRequest,
): Promise<MutationResult<UploadSessionView>> {
  const options = await authorizedOptions();
  return requestMutation(() =>
    fileUploadSessionsComplete({ ...options, path: { session_id: sessionId }, body }),
  );
}

export async function getUploadSession(sessionId: string): Promise<UploadSessionView> {
  const options = await authorizedOptions();
  return requestQueryData(() =>
    fileUploadSessionsGet({ ...options, path: { session_id: sessionId } }),
  );
}

export async function cancelUploadSession(
  sessionId: string,
): Promise<MutationResult<UploadSessionView>> {
  const options = await authorizedOptions();
  return requestMutation(() =>
    fileUploadSessionsCancel({ ...options, path: { session_id: sessionId } }),
  );
}

export async function resolveDuplicateUpload(
  sessionId: string,
  body: DuplicateResolutionRequest,
): Promise<MutationResult<UploadSessionView>> {
  const options = await authorizedOptions();
  return requestMutation(() =>
    fileUploadSessionsResolveDuplicate({ ...options, path: { session_id: sessionId }, body }),
  );
}

export async function listKnowledgeFiles({
  knowledgeBaseId,
  page = 1,
  pageSize = 20,
  search,
  status,
}: KnowledgeFileListInput): Promise<PageData<KnowledgeFileView>> {
  const options = await authorizedOptions();
  return requestPageData(() =>
    knowledgeBaseFilesList({
      ...options,
      path: { knowledge_base_id: knowledgeBaseId },
      query: {
        page,
        page_size: pageSize,
        search: search || undefined,
        status: status || undefined,
      },
    }),
  );
}

export async function updateKnowledgeFile(
  knowledgeBaseId: string,
  knowledgeFileId: string,
  body: KnowledgeFileUpdate,
): Promise<MutationResult<KnowledgeFileView>> {
  const options = await authorizedOptions();
  return requestMutation(() =>
    knowledgeBaseFilesUpdate({
      ...options,
      path: { knowledge_base_id: knowledgeBaseId, knowledge_file_id: knowledgeFileId },
      body,
    }),
  );
}

export async function moveKnowledgeFile(
  knowledgeBaseId: string,
  knowledgeFileId: string,
  body: KnowledgeFileMove,
): Promise<MutationResult<KnowledgeFileView>> {
  const options = await authorizedOptions();
  return requestMutation(() =>
    knowledgeBaseFilesMove({
      ...options,
      path: { knowledge_base_id: knowledgeBaseId, knowledge_file_id: knowledgeFileId },
      body,
    }),
  );
}

export async function getKnowledgeFileDownloadUrl(
  knowledgeBaseId: string,
  knowledgeFileId: string,
): Promise<DownloadUrlView> {
  const options = await authorizedOptions();
  return requestQueryData(() =>
    knowledgeBaseFilesDownloadUrl({
      ...options,
      path: { knowledge_base_id: knowledgeBaseId, knowledge_file_id: knowledgeFileId },
    }),
  );
}

export async function getKnowledgeFileDeletionImpact(
  knowledgeBaseId: string,
  knowledgeFileId: string,
  mode: DeleteRequest["mode"] = "SOURCE_ONLY",
): Promise<DeletionImpactView> {
  const options = await authorizedOptions();
  return requestQueryData(() =>
    knowledgeBaseFilesDeletionImpact({
      ...options,
      path: { knowledge_base_id: knowledgeBaseId, knowledge_file_id: knowledgeFileId },
      query: { mode },
    }),
  );
}

export async function deleteKnowledgeFile(
  knowledgeBaseId: string,
  knowledgeFileId: string,
  body: DeleteRequest,
): Promise<MutationResult<DeleteResult>> {
  const options = await authorizedOptions();
  return requestMutation(() =>
    knowledgeBaseFilesDelete({
      ...options,
      path: { knowledge_base_id: knowledgeBaseId, knowledge_file_id: knowledgeFileId },
      body,
    }),
  );
}

export async function putPresignedFile(
  url: string,
  body: Blob,
  contentType?: string,
): Promise<Response> {
  return putPresignedObject(url, body, contentType);
}
