import { healthReady } from "@/lib/api/generated/sdk.gen";
import type { ReadyResponse } from "@/lib/api/generated/types.gen";

export const systemHealthQueryKey = ["system", "health", "ready"] as const;

export async function getSystemHealth(): Promise<ReadyResponse> {
  const result = await healthReady({ baseUrl: "/api/backend" });
  if (result.data) {
    return result.data;
  }
  if (result.error) {
    if ("checks" in result.error) {
      return result.error;
    }
    throw new Error(result.error.message);
  }
  throw new Error("health_response_unavailable");
}
