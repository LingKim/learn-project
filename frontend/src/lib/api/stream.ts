import { ApiError, toApiError } from "./errors";

/** Shared fetch for generated SSE clients: preserve the regular Problem contract. */
export const streamFetch: typeof fetch = async (input, init) => {
  try {
    const response = await globalThis.fetch(input, init);
    if (!response.ok) {
      const problem: unknown = await response.json().catch(() => null);
      throw toApiError(problem, response);
    }
    if (!response.headers.get("content-type")?.includes("text/event-stream")) {
      throw new ApiError("接口未返回流式响应", { errorKey: "API_CONTRACT_MISMATCH" });
    }
    return response;
  } catch (error) {
    throw toApiError(error);
  }
};

/** The SDK swallows transport errors; surface them and require a terminal event. */
export async function consumeStream<T>(
  create: (onError: (error: unknown) => void) => Promise<{ stream: AsyncIterable<T> }>,
  receive: (event: T) => boolean,
  signal: AbortSignal,
): Promise<void> {
  let failure: unknown;
  try {
    const result = await create((error) => {
      failure = error;
    });
    for await (const event of result.stream) {
      if (signal.aborted) throw new DOMException("已取消", "AbortError");
      if (receive(event)) return;
    }
    if (signal.aborted) throw new DOMException("已取消", "AbortError");
    if (failure) throw failure;
    throw new ApiError("回答连接已中断，请重试。", { errorKey: "ANSWER_STREAM_INTERRUPTED" });
  } catch (error) {
    if (signal.aborted) throw new DOMException("已取消", "AbortError");
    throw toApiError(error);
  }
}
