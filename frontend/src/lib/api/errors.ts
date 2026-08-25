import type { ProblemDetails, ValidationIssue } from "@/lib/api/generated/types.gen";

type ApiErrorOptions = {
  status?: number;
  code?: number;
  errorKey?: string;
  requestId?: string;
  validationErrors?: ValidationIssue[];
  cause?: unknown;
};

export class ApiError extends Error {
  readonly status?: number;
  readonly code?: number;
  readonly errorKey?: string;
  readonly requestId?: string;
  readonly validationErrors?: ValidationIssue[];

  constructor(message: string, options: ApiErrorOptions = {}) {
    super(message, { cause: options.cause });
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.errorKey = options.errorKey;
    this.requestId = options.requestId;
    this.validationErrors = options.validationErrors;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function isProblemDetails(value: unknown): value is ProblemDetails {
  if (!isRecord(value)) return false;
  return (
    typeof value.status === "number" &&
    typeof value.code === "number" &&
    typeof value.message === "string" &&
    typeof value.title === "string" &&
    typeof value.detail === "string"
  );
}

function isValidationIssue(value: unknown): value is ValidationIssue {
  return isRecord(value) && typeof value.field === "string" && typeof value.message === "string";
}

export function toApiError(error: unknown, response?: Response): ApiError {
  if (error instanceof ApiError) return error;

  if (isProblemDetails(error)) {
    const responseStatus = response?.status ?? error.status;
    if (error.status !== error.code || responseStatus !== error.status) {
      return new ApiError("接口错误响应格式不符合约定", {
        status: responseStatus,
        code: responseStatus,
        errorKey: "API_CONTRACT_MISMATCH",
        cause: error,
      });
    }
    return new ApiError(error.message, {
      status: responseStatus,
      code: error.code,
      errorKey: error.error_key ?? undefined,
      requestId: error.request_id ?? undefined,
      validationErrors: error.errors?.filter(isValidationIssue) ?? undefined,
      cause: error,
    });
  }

  if (response) {
    return new ApiError(`请求失败（${response.status}）`, {
      status: response.status,
      code: response.status,
      errorKey: "HTTP_ERROR",
      cause: error,
    });
  }

  if (error instanceof TypeError) {
    return new ApiError("网络连接失败，请稍后重试", {
      errorKey: "NETWORK_ERROR",
      cause: error,
    });
  }

  return new ApiError("请求处理失败，请稍后重试", {
    errorKey: "UNKNOWN_ERROR",
    cause: error,
  });
}

export function toFieldErrors(error: unknown): Record<string, string> {
  const apiError = toApiError(error);
  const fieldErrors: Record<string, string> = {};
  for (const issue of apiError.validationErrors ?? []) {
    if (!(issue.field in fieldErrors)) {
      fieldErrors[issue.field] = issue.message;
    }
  }
  return fieldErrors;
}
