import { describe, expect, it } from "vitest";

import { ApiError, toApiError, toFieldErrors } from "./errors";

describe("ApiError", () => {
  it("preserves Problem Details fields", () => {
    const error = toApiError({
      type: "https://xuemian.ai/problems/validation-error",
      title: "请求参数不合法",
      status: 422,
      detail: "请求包含 1 个参数错误。",
      instance: "/api/v1/users",
      code: 422,
      message: "请求参数不合法",
      data: null,
      error_key: "VALIDATION_ERROR",
      request_id: "request-1",
      errors: [{ field: "email", message: "邮箱格式不正确" }],
    });

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 422,
      code: 422,
      message: "请求参数不合法",
      errorKey: "VALIDATION_ERROR",
      requestId: "request-1",
      validationErrors: [{ field: "email", message: "邮箱格式不正确" }],
    });
  });

  it("normalizes network errors without exposing the original message", () => {
    const error = toApiError(new TypeError("Failed to fetch secret-host.internal"));

    expect(error.message).toBe("网络连接失败，请稍后重试");
    expect(error.errorKey).toBe("NETWORK_ERROR");
    expect(error.message).not.toContain("secret-host");
  });

  it("rejects mismatched Problem Details status codes", () => {
    const error = toApiError(
      {
        type: "about:blank",
        title: "请求失败",
        status: 400,
        detail: "请求失败",
        instance: "/api/v1/test",
        code: 500,
        message: "请求失败",
        data: null,
      },
      new Response(null, { status: 400 }),
    );

    expect(error).toMatchObject({
      status: 400,
      code: 400,
      errorKey: "API_CONTRACT_MISMATCH",
    });
  });

  it("maps validation issues without binding to a form library", () => {
    const error = new ApiError("参数错误", {
      status: 422,
      validationErrors: [
        { field: "email", message: "邮箱格式不正确" },
        { field: "profile.name", message: "姓名不能为空" },
      ],
    });

    expect(toFieldErrors(error)).toEqual({
      email: "邮箱格式不正确",
      "profile.name": "姓名不能为空",
    });
  });
});
