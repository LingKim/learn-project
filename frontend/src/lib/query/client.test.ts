import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/errors";

import { mutationErrorMessage, mutationSuccessMessage } from "./client";

describe("mutation notifications", () => {
  it("uses the backend message by default and supports overrides", () => {
    const result = { data: { id: 1 }, message: "创建成功" };

    expect(mutationSuccessMessage(result, undefined)).toBe("创建成功");
    expect(mutationSuccessMessage(result, { successToast: false })).toBeUndefined();
    expect(mutationSuccessMessage(result, { successToast: "保存完成" })).toBe("保存完成");
  });

  it("leaves validation and local errors to the feature", () => {
    const validationError = new ApiError("参数错误", { status: 422 });
    const serverError = new ApiError("服务异常", { status: 500 });

    expect(mutationErrorMessage(validationError, undefined)).toBeUndefined();
    expect(mutationErrorMessage(serverError, { errorMode: "local" })).toBeUndefined();
    expect(mutationErrorMessage(serverError, undefined)).toBe("服务异常");
  });
});
