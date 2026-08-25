import { MutationCache, QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { toApiError } from "@/lib/api/errors";
import type { MutationResult } from "@/lib/api/protocol";

import { shouldRetryQuery } from "./policy";
import type { AppMutationMeta } from "./types";

function isMutationResult(value: unknown): value is MutationResult<unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    "data" in value &&
    "message" in value &&
    typeof value.message === "string"
  );
}

export function mutationSuccessMessage(
  data: unknown,
  meta: AppMutationMeta | undefined,
): string | undefined {
  if (meta?.successToast === false) return undefined;
  if (typeof meta?.successToast === "string") return meta.successToast;
  if (isMutationResult(data)) return data.message;
  if (meta?.successToast === true) return "操作成功";
  return undefined;
}

export function mutationErrorMessage(
  error: unknown,
  meta: AppMutationMeta | undefined,
): string | undefined {
  if (meta?.errorMode === "local") return undefined;
  const apiError = toApiError(error);
  if (apiError.status === 422) return undefined;
  return apiError.message;
}

export function createAppQueryClient(): QueryClient {
  return new QueryClient({
    mutationCache: new MutationCache({
      onSuccess: (data, _variables, _context, mutation) => {
        const message = mutationSuccessMessage(data, mutation.meta);
        if (message) toast.success(message);
      },
      onError: (error, _variables, _context, mutation) => {
        const message = mutationErrorMessage(error, mutation.meta);
        if (message) toast.error(message);
      },
    }),
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: false,
        retry: shouldRetryQuery,
        staleTime: 15_000,
      },
      mutations: {
        retry: false,
      },
    },
  });
}
