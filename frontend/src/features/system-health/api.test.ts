import { beforeEach, describe, expect, it, vi } from "vitest";

import { healthReady } from "@/lib/api/generated/sdk.gen";

import { getSystemHealth } from "./api";

vi.mock("@/lib/api/generated/sdk.gen", () => ({
  healthReady: vi.fn(),
}));

describe("getSystemHealth", () => {
  beforeEach(() => {
    vi.mocked(healthReady).mockReset();
  });

  it("returns readiness success data", async () => {
    const ready = { status: "ready" as const, checks: {} };
    vi.mocked(healthReady).mockResolvedValue({
      data: ready,
      error: undefined,
      request: new Request("http://localhost/api/backend/api/v1/health/ready"),
      response: new Response(),
    });

    await expect(getSystemHealth()).resolves.toEqual(ready);
  });

  it("keeps readiness 503 as degraded data", async () => {
    const degraded = { status: "degraded" as const, checks: {} };
    vi.mocked(healthReady).mockResolvedValue({
      data: undefined,
      error: degraded,
      request: new Request("http://localhost/api/backend/api/v1/health/ready"),
      response: new Response(null, { status: 503 }),
    });

    await expect(getSystemHealth()).resolves.toEqual(degraded);
  });

  it("preserves Problem Details as ApiError", async () => {
    vi.mocked(healthReady).mockResolvedValue({
      data: undefined,
      error: {
        type: "about:blank",
        title: "请求失败",
        status: 401,
        detail: "身份认证失败",
        instance: "/api/v1/health/ready",
        code: 401,
        message: "身份认证失败",
        data: null,
        error_key: "UNAUTHORIZED",
        request_id: "request-1",
      },
      request: new Request("http://localhost/api/backend/api/v1/health/ready"),
      response: new Response(null, { status: 401 }),
    });

    await expect(getSystemHealth()).rejects.toMatchObject({
      status: 401,
      errorKey: "UNAUTHORIZED",
      requestId: "request-1",
    });
  });
});
