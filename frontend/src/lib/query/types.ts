import type { ApiError } from "@/lib/api/errors";

export type AppMutationMeta = {
  successToast?: boolean | string;
  errorMode?: "global" | "local";
  [key: string]: unknown;
};

declare module "@tanstack/react-query" {
  interface Register {
    defaultError: ApiError;
    mutationMeta: AppMutationMeta;
  }
}
