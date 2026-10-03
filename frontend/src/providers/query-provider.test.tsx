import { useQuery, useQueryClient } from "@tanstack/react-query";
import { StrictMode } from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { QueryProvider } from "./query-provider";

const session = vi.hoisted(() => ({ owner: "first-owner", status: "authenticated" }));
vi.mock("@/features/auth/auth-provider", () => ({
  useAuth: () => ({ status: session.status, user: { id: session.owner } }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

beforeEach(() => {
  session.owner = "first-owner";
  session.status = "authenticated";
});
afterEach(cleanup);

it("账号改变时使用独立缓存，相同账号的重渲染保持缓存", async () => {
  const clients: ReturnType<typeof useQueryClient>[] = [];
  function Probe() {
    const client = useQueryClient();
    if (!clients.includes(client)) clients.push(client);
    const result = useQuery({
      queryKey: ["user-profile", "detail"],
      queryFn: async () => ({ owner: session.owner }),
      staleTime: Infinity,
    });
    return <p>{result.data?.owner ?? "loading"}</p>;
  }
  const view = render(
    <QueryProvider>
      <Probe />
    </QueryProvider>,
  );
  await screen.findByText("first-owner");
  view.rerender(
    <QueryProvider>
      <Probe />
    </QueryProvider>,
  );
  expect(clients).toHaveLength(1);
  session.owner = "second-owner";
  view.rerender(
    <QueryProvider>
      <Probe />
    </QueryProvider>,
  );
  await screen.findByText("second-owner");
  expect(screen.queryByText("first-owner")).not.toBeInTheDocument();
  expect(clients).toHaveLength(2);
  expect(clients[0].getQueryData(["user-profile", "detail"])).toBeUndefined();
});

it("旧账号迟到的私有查询不能填入新账号缓存", async () => {
  let resolveOld!: (value: { owner: string }) => void;
  const oldRequest = new Promise<{ owner: string }>((resolve) => {
    resolveOld = resolve;
  });
  const clients: ReturnType<typeof useQueryClient>[] = [];
  function Probe() {
    const client = useQueryClient();
    if (!clients.includes(client)) clients.push(client);
    const result = useQuery({
      queryKey: ["learning-practice", "list"],
      queryFn: () =>
        session.owner === "first-owner" ? oldRequest : Promise.resolve({ owner: session.owner }),
    });
    return <p>{result.data?.owner ?? "loading"}</p>;
  }
  const view = render(
    <QueryProvider>
      <Probe />
    </QueryProvider>,
  );
  await waitFor(() => expect(clients[0].isFetching()).toBe(1));
  session.owner = "second-owner";
  view.rerender(
    <QueryProvider>
      <Probe />
    </QueryProvider>,
  );
  await screen.findByText("second-owner");
  resolveOld({ owner: "private-old-result" });
  await waitFor(() => expect(clients[0].isFetching()).toBe(0));
  expect(clients[1].getQueryData(["learning-practice", "list"])).toEqual({ owner: "second-owner" });
  expect(screen.queryByText("private-old-result")).not.toBeInTheDocument();
});

it("退出会话立即移除上一账号的私有缓存", async () => {
  const clients: ReturnType<typeof useQueryClient>[] = [];
  function Probe() {
    const client = useQueryClient();
    if (!clients.includes(client)) clients.push(client);
    const result = useQuery({
      queryKey: ["private-history"],
      queryFn: async () => (session.status === "authenticated" ? "private-history" : "anonymous"),
      staleTime: Infinity,
    });
    return <p>{result.data ?? "loading"}</p>;
  }
  const view = render(
    <QueryProvider>
      <Probe />
    </QueryProvider>,
  );
  await screen.findByText("private-history");
  session.status = "anonymous";
  view.rerender(
    <QueryProvider>
      <Probe />
    </QueryProvider>,
  );
  await screen.findByText("anonymous");
  expect(clients[0].getQueryData(["private-history"])).toBeUndefined();
});

it("开发模式重复挂载仍能完成当前账号查询", async () => {
  function Probe() {
    const result = useQuery({
      queryKey: ["current-account"],
      queryFn: async () => session.owner,
    });
    return <p>{result.data ?? "loading"}</p>;
  }
  render(
    <StrictMode>
      <QueryProvider>
        <Probe />
      </QueryProvider>
    </StrictMode>,
  );
  await screen.findByText("first-owner");
});
