import type { ApiResponse, PageMeta, PageResponse } from "@/lib/api/generated/types.gen";

import { ApiError, toApiError } from "./errors";

export const API_BASE_URL = "/api/backend";

export type ApiEnvelope<T> = Omit<ApiResponse, "data"> & { data: T };
export type PageEnvelope<T> = Omit<PageResponse, "data"> & { data: T[] };

export type PageData<T> = {
  data: T[];
  meta: PageMeta;
};

export type MutationResult<T> = {
  data: T;
  message: string;
};

type SdkSuccess<T> = {
  data: T;
  response: Response;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function contractError(response: Response, cause: unknown): ApiError {
  return new ApiError("接口响应格式不符合约定", {
    status: response.status,
    code: response.status,
    errorKey: "API_CONTRACT_MISMATCH",
    cause,
  });
}

function requireEnvelope(value: unknown, response: Response): ApiEnvelope<unknown> {
  if (
    !isRecord(value) ||
    typeof value.code !== "number" ||
    typeof value.message !== "string" ||
    !("data" in value) ||
    value.code !== response.status
  ) {
    throw contractError(response, value);
  }
  return value as ApiEnvelope<unknown>;
}

function requirePageMeta(value: unknown, response: Response): PageMeta {
  if (
    !isRecord(value) ||
    typeof value.page !== "number" ||
    typeof value.page_size !== "number" ||
    typeof value.total !== "number" ||
    typeof value.total_pages !== "number"
  ) {
    throw contractError(response, value);
  }
  return value as PageMeta;
}

async function executeRequest<T>(request: () => Promise<SdkSuccess<T>>): Promise<SdkSuccess<T>> {
  try {
    return await request();
  } catch (error) {
    throw toApiError(error);
  }
}

export async function requestQueryData<T>(request: () => Promise<SdkSuccess<unknown>>): Promise<T> {
  const result = await executeRequest(request);
  return requireEnvelope(result.data, result.response).data as T;
}

export async function requestPageData<T>(
  request: () => Promise<SdkSuccess<unknown>>,
): Promise<PageData<T>> {
  const result = await executeRequest(request);
  const envelope = requireEnvelope(result.data, result.response);
  const meta = isRecord(result.data)
    ? requirePageMeta(result.data.meta, result.response)
    : requirePageMeta(undefined, result.response);
  if (!Array.isArray(envelope.data)) {
    throw contractError(result.response, result.data);
  }
  return { data: envelope.data as T[], meta };
}

export async function requestMutation<T>(
  request: () => Promise<SdkSuccess<unknown>>,
): Promise<MutationResult<T>> {
  const result = await executeRequest(request);
  const envelope = requireEnvelope(result.data, result.response);
  return { data: envelope.data as T, message: envelope.message };
}

export async function requestNoContent(
  request: () => Promise<SdkSuccess<unknown>>,
  message: string,
): Promise<MutationResult<void>> {
  const result = await executeRequest(request);
  if (result.response.status !== 204) {
    throw contractError(result.response, result.data);
  }
  return { data: undefined, message };
}

export async function requestBlob(request: () => Promise<SdkSuccess<unknown>>): Promise<Blob> {
  const result = await executeRequest(request);
  if (!(result.data instanceof Blob)) {
    throw contractError(result.response, result.data);
  }
  return result.data;
}
