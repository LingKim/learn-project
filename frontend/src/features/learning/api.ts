import { authenticatedAccessToken } from "@/features/auth/auth-provider";
import {
  learningConsentGet,
  learningConsentConfirm,
  learningConversationsList,
  learningConversationsCreate,
  learningConversationsGet,
  learningConversationsRename,
  learningConversationsDelete,
  learningAnswersCreate,
  learningAnswersStream,
  learningAnswersFeedback,
} from "@/lib/api/generated/sdk.gen";
import type {
  AnswerStreamEvent,
  AiConsentView,
  AiConsentRequest,
  AnswerRequest,
  ConversationCreate,
  ConversationView,
  ConversationDetail,
  FeedbackRequest,
  TurnView,
} from "@/lib/api/generated/types.gen";
import {
  API_BASE_URL,
  requestMutation,
  requestQueryData,
  requestPageData,
} from "@/lib/api/protocol";
export type {
  AnswerStreamEvent,
  AnswerRequest,
  ConversationCreate,
  ConversationView,
  ConversationDetail,
  TurnView,
};
import { consumeStream, streamFetch } from "@/lib/api/stream";
import { ApiError } from "@/lib/api/errors";

async function options() {
  return {
    baseUrl: API_BASE_URL,
    credentials: "include" as const,
    throwOnError: true as const,
    headers: { Authorization: `Bearer ${await authenticatedAccessToken()}` },
  };
}
export async function getLearningConsent() {
  const auth = await options();
  return requestQueryData<AiConsentView>(() => learningConsentGet(auth));
}
export async function confirmLearningConsent(body: AiConsentRequest) {
  const auth = await options();
  return requestMutation<AiConsentView>(() => learningConsentConfirm({ ...auth, body }));
}
export async function listConversations(page = 1) {
  const auth = await options();
  return requestPageData<ConversationView>(() =>
    learningConversationsList({ ...auth, query: { page, page_size: 20 } }),
  );
}
export async function createConversation(body: ConversationCreate) {
  const auth = await options();
  return requestMutation<ConversationView>(() => learningConversationsCreate({ ...auth, body }));
}
export async function getConversation(id: string) {
  const auth = await options();
  return requestQueryData<ConversationDetail>(() =>
    learningConversationsGet({ ...auth, path: { conversation_id: id } }),
  );
}
export async function renameConversation(id: string, title: string) {
  const auth = await options();
  return requestMutation<ConversationView>(() =>
    learningConversationsRename({ ...auth, path: { conversation_id: id }, body: { title } }),
  );
}
export async function deleteConversation(id: string) {
  const auth = await options();
  return requestMutation<null>(() =>
    learningConversationsDelete({ ...auth, path: { conversation_id: id } }),
  );
}
export async function sendQuestion(id: string, body: AnswerRequest) {
  const auth = await options();
  return requestMutation<TurnView>(() =>
    learningAnswersCreate({ ...auth, path: { conversation_id: id }, body }),
  );
}
export async function setFeedback(id: string, turnId: string, body: FeedbackRequest) {
  const auth = await options();
  return requestMutation<TurnView>(() =>
    learningAnswersFeedback({ ...auth, path: { conversation_id: id, turn_id: turnId }, body }),
  );
}

export async function streamQuestion(
  id: string,
  body: AnswerRequest,
  signal: AbortSignal,
  receive: (event: AnswerStreamEvent) => void,
) {
  const auth = await options();
  await consumeStream<AnswerStreamEvent>(
    async (onSseError) =>
      learningAnswersStream({
        ...auth,
        baseUrl: new URL(API_BASE_URL, window.location.origin).toString(),
        path: { conversation_id: id },
        body,
        signal,
        fetch: streamFetch,
        sseMaxRetryAttempts: 1,
        onSseError,
      }),
    (event) => {
      if (!event || !["started", "delta", "completed", "failed"].includes(event.type)) {
        throw new ApiError("流式事件格式不符合约定", { errorKey: "API_CONTRACT_MISMATCH" });
      }
      if (event.type === "failed")
        throw new ApiError(event.message ?? "回答未完成，请重试。", {
          errorKey: event.error_code ?? "ANSWER_FAILED",
        });
      if ((event.type === "started" || event.type === "completed") && !event.turn) {
        throw new ApiError("回答事件缺少消息", { errorKey: "API_CONTRACT_MISMATCH" });
      }
      if (
        (event.type === "delta" && typeof event.delta !== "string") ||
        (event.type === "completed" && event.turn?.status !== "succeeded")
      ) {
        throw new ApiError("流式终态格式不符合约定", { errorKey: "API_CONTRACT_MISMATCH" });
      }
      receive(event);
      return event.type === "completed";
    },
    signal,
  );
}
