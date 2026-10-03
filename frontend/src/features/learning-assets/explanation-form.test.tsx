import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ExplanationForm } from "./explanation-form";
import { syntheticWeakness } from "./fixtures.test-support";
vi.mock("@/features/user-profile/queries", () => ({
  userProfileQueryOptions: () => ({
    queryKey: ["profile"],
    queryFn: async () => ({ preferred_language: "en-US" }),
  }),
}));
vi.mock("@/features/file-management/queries", () => ({
  knowledgeBaseListQueryOptions: () => ({
    queryKey: ["bases"],
    queryFn: async () => ({ data: [] }),
  }),
  knowledgeFileListQueryOptions: () => ({
    queryKey: ["files"],
    queryFn: async () => ({ data: [] }),
  }),
}));
afterEach(cleanup);
it("默认配置不把画像兜底值当显式输入，编辑错误后保留用户草稿", () => {
  const submit = vi.fn();
  const draft = vi.fn();
  const client = new QueryClient();
  const { rerender } = render(
    <QueryClientProvider client={client}>
      <ExplanationForm pending={false} onSubmit={submit} onDraftChange={draft} />
    </QueryClientProvider>,
  );
  fireEvent.change(screen.getByLabelText("知识点"), { target: { value: "合成知识点" } });
  fireEvent.click(screen.getByRole("button", { name: "开始精讲" }));
  expect(submit.mock.calls[0][0]).toMatchObject({
    topic: "合成知识点",
    foundation: "know_concept",
    depth: "systematic",
    source_mode: "general",
  });
  expect(submit.mock.calls[0][0]).not.toHaveProperty("preferred_language");
  expect(draft.mock.calls.at(-1)?.[0].topic).toBe("合成知识点");
  rerender(
    <QueryClientProvider client={client}>
      <ExplanationForm pending={false} error="版本冲突" onSubmit={submit} />
    </QueryClientProvider>,
  );
  expect(screen.getByLabelText("知识点")).toHaveValue("合成知识点");
  expect(screen.getByRole("alert")).toHaveTextContent("版本冲突");
});
it("绑定难点时主题与资料范围不可通过表单暗中改变", () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ExplanationForm
        initial={{
          topic: syntheticWeakness.title,
          source_mode: "materials",
          knowledge_base_id: "base-1",
          file_ids: ["file-1"],
        }}
        selectedWeakness={syntheticWeakness}
        pending={false}
        onSubmit={vi.fn()}
      />
    </QueryClientProvider>,
  );
  expect(screen.getByLabelText("知识点")).toBeDisabled();
  expect(screen.getByRole("combobox", { name: "知识来源模式" })).toBeDisabled();
  expect(screen.getByRole("combobox", { name: "知识库" })).toBeDisabled();
});
