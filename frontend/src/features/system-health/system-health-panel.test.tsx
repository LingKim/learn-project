import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { healthReady } from "@/lib/api/generated/sdk.gen";

import { SystemHealthPanel } from "./system-health-panel";

vi.mock("@/lib/api/generated/sdk.gen", () => ({
  healthReady: vi.fn(),
}));

describe("SystemHealthPanel", () => {
  it("shows every dependency when the backend reports ready", async () => {
    vi.mocked(healthReady).mockResolvedValue({
      data: {
        status: "ready",
        checks: {
          postgresql: { status: "up", code: "ok" },
          redis: { status: "up", code: "ok" },
          rustfs: { status: "up", code: "ok" },
        },
      },
      error: undefined,
      request: new Request("http://localhost/api/backend/api/v1/health/ready"),
      response: new Response(),
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
});
