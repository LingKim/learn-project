import { mutationOptions, queryOptions, type QueryClient } from "@tanstack/react-query";

import {
  getAIProcessingConsent,
  confirmAIProcessingConsent,
  getDocumentProcessingTask,
  startDocumentProcessing,
  cancelDocumentProcessing,
  searchDocumentEvidence,
  type AIConsentRequest,
  type RetrievalRequest,
  createKnowledgeBase,
  deleteKnowledgeBase,
  deleteKnowledgeFile,
  getKnowledgeFileDownloadUrl,
  getKnowledgeBaseDeletionImpact,
  getKnowledgeFileDeletionImpact,
  listKnowledgeBases,
  getKnowledgeBaseStatistics,
  listKnowledgeFiles,
  moveKnowledgeFile,
  updateKnowledgeBase,
  updateKnowledgeFile,
  type DeleteRequest,
  type KnowledgeBaseCreate,
  type KnowledgeBaseUpdate,
  type KnowledgeFileMove,
  type KnowledgeFileUpdate,
} from "./api";
import { uploadKnowledgeFile, type UploadKnowledgeFileInput } from "./upload";

type DeletionMode = NonNullable<DeleteRequest["mode"]>;

export const fileManagementKeys = {
  all: ["file-management"] as const,
  consent: () => [...fileManagementKeys.all, "ai-consent"] as const,
  processing: (kb: string, file: string) =>
    [...fileManagementKeys.files(kb), file, "processing"] as const,
  knowledgeBases: () => [...fileManagementKeys.all, "knowledge-bases"] as const,
  statistics: () => [...fileManagementKeys.knowledgeBases(), "statistics"] as const,
  knowledgeBaseList: (page: number, pageSize: number) =>
    [...fileManagementKeys.knowledgeBases(), "list", page, pageSize] as const,
  knowledgeBaseImpact: (knowledgeBaseId: string, mode: DeletionMode) =>
    [...fileManagementKeys.knowledgeBases(), knowledgeBaseId, "deletion-impact", mode] as const,
  files: (knowledgeBaseId: string) =>
    [...fileManagementKeys.all, "knowledge-bases", knowledgeBaseId, "files"] as const,
  fileList: (
    knowledgeBaseId: string,
    page: number,
    pageSize: number,
    search: string,
    status: string,
    fileFormat = "",
    sort = "updated",
  ) =>
    [
      ...fileManagementKeys.files(knowledgeBaseId),
      "list",
      page,
      pageSize,
      search,
      status,
      fileFormat,
      sort,
    ] as const,
  fileImpact: (knowledgeBaseId: string, knowledgeFileId: string, mode: DeletionMode) =>
    [
      ...fileManagementKeys.files(knowledgeBaseId),
      knowledgeFileId,
      "deletion-impact",
      mode,
    ] as const,
};

export function knowledgeBaseListQueryOptions(page = 1, pageSize = 20) {
  return queryOptions({
    queryKey: fileManagementKeys.knowledgeBaseList(page, pageSize),
    queryFn: () => listKnowledgeBases({ page, pageSize }),
  });
}

export function knowledgeBaseStatisticsQueryOptions() {
  return queryOptions({
    queryKey: fileManagementKeys.statistics(),
    queryFn: getKnowledgeBaseStatistics,
    refetchInterval: (query) => (query.state.data?.processing_file_count ? 3000 : false),
  });
}

export function knowledgeFileListQueryOptions(
  knowledgeBaseId: string,
  page = 1,
  pageSize = 20,
  search = "",
  status = "",
  fileFormat?: "pdf" | "docx" | "txt" | "md",
  sort: "updated" | "name" = "updated",
) {
  return queryOptions({
    queryKey: fileManagementKeys.fileList(
      knowledgeBaseId,
      page,
      pageSize,
      search,
      status,
      fileFormat,
      sort,
    ),
    queryFn: () =>
      listKnowledgeFiles({ knowledgeBaseId, page, pageSize, search, status, fileFormat, sort }),
    refetchInterval: (query) =>
      query.state.data?.data.some((file) =>
        ["pending_processing", "processing"].includes(file.processing_status),
      )
        ? 3000
        : false,
  });
}

export function knowledgeBaseDeletionImpactQueryOptions(
  knowledgeBaseId: string,
  mode: DeletionMode = "SOURCE_ONLY",
) {
  return queryOptions({
    queryKey: fileManagementKeys.knowledgeBaseImpact(knowledgeBaseId, mode),
    queryFn: () => getKnowledgeBaseDeletionImpact(knowledgeBaseId, mode),
    enabled: Boolean(knowledgeBaseId),
    staleTime: 0,
  });
}

export function knowledgeFileDeletionImpactQueryOptions(
  knowledgeBaseId: string,
  knowledgeFileId: string,
  mode: DeletionMode = "SOURCE_ONLY",
) {
  return queryOptions({
    queryKey: fileManagementKeys.fileImpact(knowledgeBaseId, knowledgeFileId, mode),
    queryFn: () => getKnowledgeFileDeletionImpact(knowledgeBaseId, knowledgeFileId, mode),
    enabled: Boolean(knowledgeBaseId && knowledgeFileId),
    staleTime: 0,
  });
}

export function createKnowledgeBaseMutationOptions(queryClient: QueryClient) {
  return mutationOptions({
    mutationKey: [...fileManagementKeys.knowledgeBases(), "create"],
    mutationFn: (body: KnowledgeBaseCreate) => createKnowledgeBase(body),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: fileManagementKeys.knowledgeBases() }),
  });
}

export function updateKnowledgeBaseMutationOptions(queryClient: QueryClient) {
  return mutationOptions({
    mutationKey: [...fileManagementKeys.knowledgeBases(), "update"],
    mutationFn: ({ id, body }: { id: string; body: KnowledgeBaseUpdate }) =>
      updateKnowledgeBase(id, body),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: fileManagementKeys.knowledgeBases() }),
  });
}

export function deleteKnowledgeBaseMutationOptions(queryClient: QueryClient) {
  return mutationOptions({
    mutationKey: [...fileManagementKeys.knowledgeBases(), "delete"],
    mutationFn: ({ id, body }: { id: string; body: DeleteRequest }) =>
      deleteKnowledgeBase(id, body),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: fileManagementKeys.knowledgeBases() }),
  });
}

export function uploadKnowledgeFileMutationOptions(queryClient: QueryClient) {
  return mutationOptions({
    mutationKey: [...fileManagementKeys.all, "upload"],
    mutationFn: (input: UploadKnowledgeFileInput) => uploadKnowledgeFile(input),
    onSuccess: (_result, input) =>
      Promise.all([
        queryClient.invalidateQueries({
          queryKey: fileManagementKeys.files(input.knowledgeBaseId),
        }),
        queryClient.invalidateQueries({ queryKey: fileManagementKeys.statistics() }),
      ]),
  });
}

export function updateKnowledgeFileMutationOptions(queryClient: QueryClient) {
  return mutationOptions({
    mutationKey: [...fileManagementKeys.all, "file", "update"],
    mutationFn: ({
      knowledgeBaseId,
      knowledgeFileId,
      body,
    }: {
      knowledgeBaseId: string;
      knowledgeFileId: string;
      body: KnowledgeFileUpdate;
    }) => updateKnowledgeFile(knowledgeBaseId, knowledgeFileId, body),
    onSuccess: (_result, input) =>
      Promise.all([
        queryClient.invalidateQueries({
          queryKey: fileManagementKeys.files(input.knowledgeBaseId),
        }),
        queryClient.invalidateQueries({ queryKey: fileManagementKeys.statistics() }),
      ]),
  });
}

export function moveKnowledgeFileMutationOptions(queryClient: QueryClient) {
  return mutationOptions({
    mutationKey: [...fileManagementKeys.all, "file", "move"],
    mutationFn: ({
      knowledgeBaseId,
      knowledgeFileId,
      body,
    }: {
      knowledgeBaseId: string;
      knowledgeFileId: string;
      body: KnowledgeFileMove;
    }) => moveKnowledgeFile(knowledgeBaseId, knowledgeFileId, body),
    onSuccess: (_result, input) =>
      Promise.all([
        queryClient.invalidateQueries({
          queryKey: fileManagementKeys.files(input.knowledgeBaseId),
        }),
        queryClient.invalidateQueries({
          queryKey: fileManagementKeys.files(input.body.target_knowledge_base_id),
        }),
        queryClient.invalidateQueries({ queryKey: fileManagementKeys.statistics() }),
      ]),
  });
}

export function deleteKnowledgeFileMutationOptions(queryClient: QueryClient) {
  return mutationOptions({
    mutationKey: [...fileManagementKeys.all, "file", "delete"],
    mutationFn: ({
      knowledgeBaseId,
      knowledgeFileId,
      body,
    }: {
      knowledgeBaseId: string;
      knowledgeFileId: string;
      body: DeleteRequest;
    }) => deleteKnowledgeFile(knowledgeBaseId, knowledgeFileId, body),
    onSuccess: (_result, input) =>
      Promise.all([
        queryClient.invalidateQueries({
          queryKey: fileManagementKeys.files(input.knowledgeBaseId),
        }),
        queryClient.invalidateQueries({ queryKey: fileManagementKeys.statistics() }),
      ]),
  });
}

export function downloadKnowledgeFileMutationOptions() {
  return mutationOptions({
    mutationKey: [...fileManagementKeys.all, "file", "download"],
    mutationFn: ({
      knowledgeBaseId,
      knowledgeFileId,
    }: {
      knowledgeBaseId: string;
      knowledgeFileId: string;
    }) => getKnowledgeFileDownloadUrl(knowledgeBaseId, knowledgeFileId),
    meta: { successToast: false },
  });
}

export function aiConsentQueryOptions() {
  return queryOptions({
    queryKey: fileManagementKeys.consent(),
    queryFn: getAIProcessingConsent,
    staleTime: 300_000,
  });
}
export function confirmAIConsentMutationOptions(queryClient: QueryClient) {
  return mutationOptions({
    mutationKey: [...fileManagementKeys.all, "confirm-ai-consent"],
    mutationFn: (body: AIConsentRequest) => confirmAIProcessingConsent(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: fileManagementKeys.all }),
  });
}
export function processingTaskQueryOptions(kb: string, file: string) {
  return queryOptions({
    queryKey: fileManagementKeys.processing(kb, file),
    queryFn: () => getDocumentProcessingTask(kb, file),
    refetchInterval: (query) =>
      query.state.data &&
      !query.state.data.requires_ai_consent &&
      ["pending", "processing", "cancel_requested"].includes(query.state.data.status)
        ? 2000
        : false,
  });
}
export function processingMutationOptions(queryClient: QueryClient, action: "start" | "cancel") {
  return mutationOptions({
    mutationKey: [...fileManagementKeys.all, "processing", action],
    mutationFn: ({ kb, file }: { kb: string; file: string }) =>
      action === "start" ? startDocumentProcessing(kb, file) : cancelDocumentProcessing(kb, file),
    onSuccess: (_data, input) =>
      queryClient.invalidateQueries({ queryKey: fileManagementKeys.files(input.kb) }),
  });
}
export function documentRetrievalMutationOptions() {
  return mutationOptions({
    mutationKey: [...fileManagementKeys.all, "retrieval"],
    mutationFn: ({ kb, body }: { kb: string; body: RetrievalRequest }) =>
      searchDocumentEvidence(kb, body),
    meta: { successToast: false },
  });
}
