import { healthReady } from "@/lib/api/generated/sdk.gen";
import type { ReadyResponse } from "@/lib/api/generated/types.gen";
import { API_BASE_URL } from "@/lib/api/protocol";
import { toApiError } from "@/lib/api/errors";

export type { DependencyCheck, ReadyResponse } from "@/lib/api/generated/types.gen";

function isReadyResponse(value: unknown): value is ReadyResponse {
  return (
    typeof value === "object" &&
    value !== null &&
    "status" in value &&
    (value.status === "ready" || value.status === "degraded") &&
    "checks" in value &&
    typeof value.checks === "object" &&
    value.checks !== null
  );
}

export async function getSystemHealth(): Promise<ReadyResponse> {
  const result = await healthReady({ baseUrl: API_BASE_URL });
  if (result.data) {
    return result.data;
  }
  if (isReadyResponse(result.error)) {
    return result.error;
  }
  throw toApiError(result.error, result.response);
}
