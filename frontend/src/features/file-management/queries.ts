import { mutationOptions, queryOptions, type QueryClient } from "@tanstack/react-query";

import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  deleteKnowledgeFile,
  getKnowledgeFileDownloadUrl,
  getKnowledgeBaseDeletionImpact,
  getKnowledgeFileDeletionImpact,
  listKnowledgeBases,
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
  knowledgeBases: () => [...fileManagementKeys.all, "knowledge-bases"] as const,
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
  ) =>
    [...fileManagementKeys.files(knowledgeBaseId), "list", page, pageSize, search, status] as const,
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

export function knowledgeFileListQueryOptions(
  knowledgeBaseId: string,
  page = 1,
  pageSize = 20,
  search = "",
  status = "",
) {
  return queryOptions({
    queryKey: fileManagementKeys.fileList(knowledgeBaseId, page, pageSize, search, status),
    queryFn: () => listKnowledgeFiles({ knowledgeBaseId, page, pageSize, search, status }),
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
      queryClient.invalidateQueries({ queryKey: fileManagementKeys.files(input.knowledgeBaseId) }),
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
      queryClient.invalidateQueries({ queryKey: fileManagementKeys.files(input.knowledgeBaseId) }),
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
    onSuccess: (_result, input) => {
      void queryClient.invalidateQueries({
        queryKey: fileManagementKeys.files(input.knowledgeBaseId),
      });
      return queryClient.invalidateQueries({
        queryKey: fileManagementKeys.files(input.body.target_knowledge_base_id),
      });
    },
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
      queryClient.invalidateQueries({ queryKey: fileManagementKeys.files(input.knowledgeBaseId) }),
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
