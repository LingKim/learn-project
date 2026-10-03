import { afterEach, expect, it, vi } from "vitest";

const refreshSession = vi.hoisted(() => vi.fn());
vi.mock("./api", () => ({ refreshSession, getCurrentUser: vi.fn(), logoutSession: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: vi.fn() }));

afterEach(() => {
  vi.useRealTimers();
  vi.resetModules();
  vi.clearAllMocks();
});

it("refreshes expired access tokens once while sharing concurrent requests", async () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-03T00:00:00Z"));
  refreshSession
    .mockResolvedValueOnce({ data: { access_token: "first", expires_in: 60 } })
    .mockResolvedValueOnce({ data: { access_token: "second", expires_in: 60 } });
  const { authenticatedAccessToken } = await import("./auth-provider");
  expect(await authenticatedAccessToken()).toBe("first");
  expect(await authenticatedAccessToken()).toBe("first");
  expect(refreshSession).toHaveBeenCalledTimes(1);
  vi.advanceTimersByTime(31_000);
  expect(await Promise.all([authenticatedAccessToken(), authenticatedAccessToken()])).toEqual([
    "second",
    "second",
  ]);
  expect(refreshSession).toHaveBeenCalledTimes(2);
});
