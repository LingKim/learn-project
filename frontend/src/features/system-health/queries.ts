import { queryOptions } from "@tanstack/react-query";

import { getSystemHealth } from "./api";

export const systemHealthKeys = {
  all: ["system", "health"] as const,
  readiness: () => [...systemHealthKeys.all, "ready"] as const,
};

export function systemHealthQueryOptions() {
  return queryOptions({
    queryKey: systemHealthKeys.readiness(),
    queryFn: getSystemHealth,
    refetchInterval: 30_000,
    retry: false,
  });
}
