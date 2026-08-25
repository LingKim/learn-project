import { toApiError } from "@/lib/api/errors";

const RETRYABLE_STATUS_CODES = new Set([502, 503, 504]);

export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  if (failureCount >= 2) return false;
  const apiError = toApiError(error);
  return (
    apiError.errorKey === "NETWORK_ERROR" ||
    (apiError.status !== undefined && RETRYABLE_STATUS_CODES.has(apiError.status))
  );
}
