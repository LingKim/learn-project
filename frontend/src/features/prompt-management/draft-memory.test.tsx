import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useAuth } from "@/features/auth/auth-provider";
import { PromptDraftScope, usePromptDraftMemory } from "./draft-memory";
import { definition, draft } from "./fixtures.test-support";
import { VersionEditor } from "./version-editor";

vi.mock("./api", () => ({
  getPromptDiff: vi.fn(),
  patchPromptDraft: vi.fn(),
  previewPromptVersion: vi.fn(),
  evaluatePromptVersion: vi.fn(),
  publishPromptVersion: vi.fn(),
  rollbackPromptDefinition: vi.fn(),
  setPromptDefinitionStatus: vi.fn(),
}));
vi.mock("@/features/auth/auth-provider", () => ({ useAuth: vi.fn() }));
const adminAuth = (id: string): ReturnType<typeof useAuth> => ({
  status: "authenticated",
  user: { id, username: id, nickname: "合成管理员", role: "admin", status: "active" },
  completeAuthentication: vi.fn(),
  logout: vi.fn(),
});
beforeEach(() => vi.mocked(useAuth).mockReturnValue(adminAuth("admin-a")));
afterEach(cleanup);

it("后台范围保留未保存输入及原修订，历史返回可恢复；范围卸载立即销毁", async () => {
  const client = new QueryClient();
  let memory!: ReturnType<typeof usePromptDraftMemory>;
  function Capture() {
    memory = usePromptDraftMemory();
    return null;
  }
  function Content({ show }: { show: boolean }) {
    return (
      <QueryClientProvider client={client}>
        <PromptDraftScope>
          <Capture />
          {show ? (
            <VersionEditor
              definition={definition}
              version={draft}
              timeline={[draft]}
              onDirty={vi.fn()}
              onReload={vi.fn()}
              onVersion={vi.fn()}
            />
          ) : (
            <p>另一个后台页面</p>
          )}
        </PromptDraftScope>
      </QueryClientProvider>
    );
  }
  const storage = vi.spyOn(Storage.prototype, "setItem");
  const view = render(<Content show />);
  fireEvent.change(screen.getByLabelText("Prompt 正文"), {
    target: { value: "会话内未保存的合成编辑" },
  });
  await waitFor(() => expect(memory.read("draft")?.form.content).toBe("会话内未保存的合成编辑"));
  view.rerender(<Content show={false} />);
  expect(screen.getByText("另一个后台页面")).toBeInTheDocument();
  view.rerender(<Content show />);
  expect(screen.getByLabelText("Prompt 正文")).toHaveValue("会话内未保存的合成编辑");
  expect(
    screen.getByText("已恢复此后台会话的未保存草稿，原编辑基准保持不变。"),
  ).toBeInTheDocument();
  expect(memory.read("draft")?.revision).toBe(2);
  expect(memory.selected("definition")).toBe("draft");
  expect(storage).not.toHaveBeenCalled();
  view.unmount();
  expect(memory.read("draft")).toBeUndefined();
  expect(memory.selected("definition")).toBeUndefined();
  client.clear();
});

it("管理员直接身份切换同步建立空scope；同ID角色失效也销毁正文", async () => {
  const client = new QueryClient();
  let memory!: ReturnType<typeof usePromptDraftMemory>;
  function Capture() {
    memory = usePromptDraftMemory();
    return null;
  }
  const content = () => (
    <QueryClientProvider client={client}>
      <PromptDraftScope>
        <Capture />
        <VersionEditor
          definition={definition}
          version={draft}
          timeline={[draft]}
          onDirty={vi.fn()}
          onReload={vi.fn()}
          onVersion={vi.fn()}
        />
      </PromptDraftScope>
    </QueryClientProvider>
  );
  const view = render(content());
  fireEvent.change(screen.getByLabelText("Prompt 正文"), {
    target: { value: "管理员A未保存的合成输入" },
  });
  await waitFor(() => expect(memory.read("draft")).toBeDefined());
  const first = memory;
  vi.mocked(useAuth).mockReturnValue(adminAuth("admin-b"));
  view.rerender(content());
  expect(screen.getByLabelText("Prompt 正文")).toHaveValue("合成旧正文");
  expect(memory.read("draft")).toBeUndefined();
  expect(first.read("draft")).toBeUndefined();
  fireEvent.change(screen.getByLabelText("Prompt 正文"), {
    target: { value: "管理员B未保存的合成输入" },
  });
  await waitFor(() => expect(memory.read("draft")).toBeDefined());
  const second = memory;
  const ordinary = adminAuth("admin-b");
  ordinary.user = { ...ordinary.user!, role: "user" };
  vi.mocked(useAuth).mockReturnValue(ordinary);
  view.rerender(content());
  expect(screen.queryByLabelText("Prompt 正文")).not.toBeInTheDocument();
  expect(second.read("draft")).toBeUndefined();
  client.clear();
});
