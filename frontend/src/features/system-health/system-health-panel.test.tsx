import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { getSystemHealth } from "./api";
import { SystemHealthPanel } from "./system-health-panel";

vi.mock("./api", () => ({
  getSystemHealth: vi.fn(),
}));

describe("SystemHealthPanel", () => {
  it("shows every dependency when the backend reports ready", async () => {
    vi.mocked(getSystemHealth).mockResolvedValue({
      status: "ready",
      checks: {
        postgresql: { status: "up", code: "ok" },
        redis: { status: "up", code: "ok" },
        rustfs: { status: "up", code: "ok" },
      },
    });
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <SystemHealthPanel />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("全部就绪")).toBeInTheDocument();
    expect(screen.getByText("PostgreSQL")).toBeInTheDocument();
    expect(screen.getByText("Redis")).toBeInTheDocument();
    expect(screen.getByText("RustFS")).toBeInTheDocument();
  });

  it("shows degraded dependencies from the readiness 503 response", async () => {
    vi.mocked(getSystemHealth).mockResolvedValue({
      status: "degraded",
      checks: {
        postgresql: { status: "up", code: "ok" },
        redis: { status: "down", code: "redis_unavailable" },
        rustfs: { status: "up", code: "ok" },
      },
    });
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <SystemHealthPanel />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("存在异常")).toBeInTheDocument();
    expect(screen.getByText("不可用")).toBeInTheDocument();
  });
});
