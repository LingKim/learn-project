import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ConfigForm } from "./config-form";
import { configForEditing } from "./config-editing";
import type { PracticeConfig } from "./api";
vi.mock("@/features/user-profile/queries", () => ({
  userProfileQueryOptions: () => ({
    queryKey: ["profile"],
    queryFn: async () => ({
      target_job: "Java 工程师",
      target_skills: ["Java"],
      experience_months: 36,
      focus_topics: ["事务"],
      preferred_language: "zh-CN",
    }),
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
function mount(initial?: PracticeConfig) {
  const confirm = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ConfigForm initial={initial} pending={false} error={null} onConfirm={confirm} />
    </QueryClientProvider>,
  );
  return confirm;
}
it("重新编辑保留画像字段presence：省略继续兜底，显式null和空数组保持清空", async () => {
  const persisted: PracticeConfig = {
    topic: "合成知识点",
    source_mode: "general",
    question_count: 1,
    question_types: { short_answer: 1 },
    target_job: null,
    target_level: null,
    experience_months: null,
    target_skills: [],
    focus_topics: null,
    learning_goal: null,
    preferred_language: null,
  };
  const initial = configForEditing({
    config: persisted,
    profile_override_fields: ["target_job", "target_skills"],
  });
  expect(initial).toEqual({
    topic: "合成知识点",
    source_mode: "general",
    question_count: 1,
    question_types: { short_answer: 1 },
    target_job: null,
    target_skills: [],
  });
  expect(persisted).toHaveProperty("experience_months", null);
  const confirm = mount(initial);
  await waitFor(() => expect(screen.getByLabelText("关注知识点")).toHaveValue("事务"));
  expect(screen.getByLabelText("目标岗位")).toHaveValue("");
  expect(screen.getByLabelText("技术栈")).toHaveValue("");
  fireEvent.click(screen.getByRole("button", { name: "生成题目方案" }));
  expect(confirm.mock.calls[0][0]).toMatchObject({ target_job: null, target_skills: [] });
  expect(confirm.mock.calls[0][0]).not.toHaveProperty("focus_topics");
  expect(confirm.mock.calls[0][0]).not.toHaveProperty("experience_months");
});
it("未修改画像字段省略，明确清空用null或空数组，技术栈逗号可继续输入", async () => {
  const confirm = mount();
  await waitFor(() => expect(screen.getByLabelText("目标岗位")).toHaveValue("Java 工程师"));
  fireEvent.change(screen.getByLabelText("知识点"), { target: { value: "合成知识点" } });
  fireEvent.click(screen.getByRole("button", { name: "生成题目方案" }));
  expect(confirm.mock.calls[0][0]).not.toHaveProperty("target_job");
  expect(confirm.mock.calls[0][0]).not.toHaveProperty("target_skills");
  expect(confirm.mock.calls[0][0]).not.toHaveProperty("experience_months");
  fireEvent.change(screen.getByLabelText("目标岗位"), { target: { value: "" } });
  fireEvent.change(screen.getByLabelText("技术栈"), { target: { value: "Java," } });
  expect(screen.getByLabelText("技术栈")).toHaveValue("Java,");
  fireEvent.change(screen.getByLabelText("技术栈"), { target: { value: "" } });
  fireEvent.change(screen.getByLabelText("关注知识点"), { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "生成题目方案" }));
  expect(confirm.mock.calls[1][0]).toMatchObject({
    target_job: null,
    target_skills: [],
    focus_topics: [],
  });
});
it("不把题型数量不匹配的配置交给模型", () => {
  const confirm = mount();
  fireEvent.change(screen.getByLabelText("题量"), { target: { value: "4" } });
  fireEvent.click(screen.getByRole("button", { name: "生成题目方案" }));
  expect(confirm).not.toHaveBeenCalled();
  expect(screen.getByRole("alert")).toHaveTextContent("各题型数量之和应等于题量");
});
