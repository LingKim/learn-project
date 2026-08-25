import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/errors";

import { shouldRetryQuery } from "./policy";

describe("query retry policy", () => {
  it.each([400, 401, 403, 404, 409, 422, 500])("does not retry HTTP %s", (status) => {
    expect(shouldRetryQuery(0, new ApiError("失败", { status }))).toBe(false);
  });

  it.each([502, 503, 504])("retries HTTP %s at most twice", (status) => {
    const error = new ApiError("暂时不可用", { status });
    expect(shouldRetryQuery(0, error)).toBe(true);
    expect(shouldRetryQuery(1, error)).toBe(true);
    expect(shouldRetryQuery(2, error)).toBe(false);
  });

  it("retries normalized network errors", () => {
    const error = new ApiError("网络错误", { errorKey: "NETWORK_ERROR" });
    expect(shouldRetryQuery(0, error)).toBe(true);
  });
});
