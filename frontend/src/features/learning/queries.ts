import { mutationOptions, queryOptions, type QueryClient } from "@tanstack/react-query";
import {
  uploadAttachment,
  deleteAttachment,
  getAttachmentContent,
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  renameConversation,
  sendQuestion,
  streamQuestion,
  type AnswerStreamEvent,
  getLearningConsent,
  confirmLearningConsent,
  setFeedback,
  type ConversationCreate,
  type AnswerRequest,
} from "./api";
import type { AIConsentRequest } from "@/features/file-management/api";
export const learningKeys = {
  all: ["learning"] as const,
  lists: () => ["learning", "conversations", "list"] as const,
  list: (page: number) => [...learningKeys.lists(), page] as const,
  detail: (id: string) => ["learning", "conversations", "detail", id] as const,
  attachment: (id: string) => ["learning", "attachments", id] as const,
  consent: () => ["learning", "consent"] as const,
};
export function conversationsQueryOptions(page = 1) {
  return queryOptions({
    queryKey: learningKeys.list(page),
    queryFn: () => listConversations(page),
  });
}
export function conversationQueryOptions(id: string) {
  return queryOptions({
    queryKey: learningKeys.detail(id),
    queryFn: () => getConversation(id),
    enabled: Boolean(id),
    refetchInterval: (query) =>
      query.state.data?.turns.some((t) => t.status === "processing") ? 3000 : false,
  });
}
export function learningConsentQueryOptions() {
  return queryOptions({ queryKey: learningKeys.consent(), queryFn: getLearningConsent });
}
async function refresh(client: QueryClient, id?: string) {
  await Promise.all([
    client.invalidateQueries({ queryKey: learningKeys.lists() }),
    ...(id ? [client.invalidateQueries({ queryKey: learningKeys.detail(id) })] : []),
  ]);
}
export function createConversationMutationOptions(client: QueryClient) {
  return mutationOptions({
    mutationKey: [...learningKeys.all, "create"],
    mutationFn: (body: ConversationCreate) => createConversation(body),
    onSuccess: () => refresh(client),
    meta: { successToast: false },
  });
}
export function sendQuestionMutationOptions(client: QueryClient) {
  return mutationOptions({
    mutationKey: [...learningKeys.all, "answer"],
    mutationFn: ({ id, body }: { id: string; body: AnswerRequest }) => sendQuestion(id, body),
    onSettled: (_data, _error, input) => refresh(client, input.id),
    meta: { successToast: false },
  });
}
export function renameConversationMutationOptions(client: QueryClient) {
  return mutationOptions({
    mutationKey: [...learningKeys.all, "rename"],
    mutationFn: ({ id, title }: { id: string; title: string }) => renameConversation(id, title),
    onSuccess: (_data, input) => refresh(client, input.id),
  });
}
export function deleteConversationMutationOptions(client: QueryClient) {
  return mutationOptions({
    mutationKey: [...learningKeys.all, "delete"],
    mutationFn: deleteConversation,
    onSuccess: async (_data, id) => {
      client.removeQueries({ queryKey: learningKeys.detail(id) });
      await refresh(client);
    },
  });
}
export function confirmLearningConsentMutationOptions(client: QueryClient) {
  return mutationOptions({
    mutationKey: [...learningKeys.all, "confirm-consent"],
    mutationFn: (body: AIConsentRequest) => confirmLearningConsent(body),
    onSuccess: () => client.invalidateQueries({ queryKey: learningKeys.consent() }),
  });
}
export function feedbackMutationOptions(client: QueryClient) {
  return mutationOptions({
    mutationKey: [...learningKeys.all, "feedback"],
    mutationFn: ({
      id,
      turnId,
      feedback,
    }: {
      id: string;
      turnId: string;
      feedback: "helpful" | "unhelpful" | null;
    }) => setFeedback(id, turnId, { feedback }),
    onSuccess: (_data, input) => refresh(client, input.id),
    meta: { successToast: false },
  });
}

export function streamQuestionMutationOptions(client: QueryClient) {
  return mutationOptions({
    mutationKey: [...learningKeys.all, "answer-stream"],
    mutationFn: ({
      id,
      body,
      signal,
      receive,
    }: {
      id: string;
      body: AnswerRequest;
      signal: AbortSignal;
      receive: (event: AnswerStreamEvent) => void;
    }) => streamQuestion(id, body, signal, receive),
    onSettled: (_data, _error, input) => refresh(client, input.id),
    retry: false,
    meta: { successToast: false, errorMode: "local" },
  });
}

export function uploadAttachmentMutationOptions() {
  return mutationOptions({
    mutationKey: [...learningKeys.all, "attachment-upload"],
    mutationFn: (file: File) => uploadAttachment(file),
    retry: false,
    meta: { successToast: false, errorMode: "local" },
  });
}
export function deleteAttachmentMutationOptions() {
  return mutationOptions({
    mutationKey: [...learningKeys.all, "attachment-delete"],
    mutationFn: (id: string) => deleteAttachment(id),
    retry: false,
    meta: { successToast: false, errorMode: "local" },
  });
}
export function attachmentContentQueryOptions(id: string) {
  return queryOptions({
    queryKey: learningKeys.attachment(id),
    queryFn: ({ signal }) => getAttachmentContent(id, signal),
    gcTime: 0,
    staleTime: 0,
    retry: false,
  });
}
