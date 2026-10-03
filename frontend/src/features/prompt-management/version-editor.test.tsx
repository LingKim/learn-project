import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import * as api from "./api";
import { definition, draft, evaluation } from "./fixtures.test-support";
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
let client: QueryClient;
beforeEach(() => {
  client = new QueryClient();
  vi.clearAllMocks();
});
afterEach(() => {
  cleanup();
  client.clear();
});
function editor(version = draft, currentDefinition = definition, onVersion = vi.fn()) {
  return render(
    <QueryClientProvider client={client}>
      <VersionEditor
        definition={currentDefinition}
        version={version}
        timeline={[version]}
        onDirty={vi.fn()}
        onReload={vi.fn()}
        onVersion={onVersion}
      />
    </QueryClientProvider>,
  );
}

it("保存草稿不调用模型，版本冲突保留正文和变更说明", async () => {
  vi.mocked(api.patchPromptDraft).mockRejectedValue(
    new ApiError("版本冲突", { status: 409, errorKey: "PROMPT_VERSION_CONFLICT" }),
  );
  editor();
  fireEvent.change(screen.getByLabelText("Prompt 正文"), {
    target: { value: "管理员未保存的合成修改" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("当前输入已保留"));
  expect(screen.getByLabelText("Prompt 正文")).toHaveValue("管理员未保存的合成修改");
  expect(screen.getByLabelText("变更说明")).toHaveValue("合成变更");
  expect(api.patchPromptDraft).toHaveBeenCalledWith(
    "draft",
    expect.objectContaining({ expected_revision: 2 }),
  );
  expect(api.evaluatePromptVersion).not.toHaveBeenCalled();
  expect(api.previewPromptVersion).not.toHaveBeenCalled();
});

it("发布确认使用草稿创建时基准，不静默采用当前活动指针；409不重发", async () => {
  vi.mocked(api.publishPromptVersion).mockRejectedValue(new ApiError("版本冲突", { status: 409 }));
  editor();
  fireEvent.click(screen.getByRole("button", { name: "发布此版本" }));
  expect(screen.getByRole("dialog")).toHaveTextContent("active-old");
  fireEvent.click(screen.getByRole("button", { name: "确认操作" }));
  await waitFor(() => expect(api.publishPromptVersion).toHaveBeenCalledTimes(1));
  expect(api.publishPromptVersion).toHaveBeenCalledWith("draft", {
    expected_active_version_id: "active-old",
    expected_revision: 2,
  });
  await waitFor(() => expect(screen.getByRole("dialog")).toHaveTextContent("当前输入已保留"));
});

it("回滚必须输入原因且选择新版本响应，不重新激活历史ID", async () => {
  const historical: api.VersionView = { ...draft, id: "historic", status: "retired", version: 1 };
  vi.mocked(api.rollbackPromptDefinition).mockResolvedValue({
    data: { ...draft, id: "new-version", version: 4 },
    message: "已创建新版本",
  });
  const onVersion = vi.fn();
  editor(historical, definition, onVersion);
  fireEvent.click(screen.getByRole("button", { name: "回滚为新版本" }));
  expect(screen.getByRole("button", { name: "确认操作" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("回滚原因（必填）"), {
    target: { value: "合成修复原因" },
  });
  fireEvent.click(screen.getByRole("button", { name: "确认操作" }));
  await waitFor(() => expect(onVersion).toHaveBeenCalledWith("new-version"));
  expect(api.rollbackPromptDefinition).toHaveBeenCalledWith("definition", {
    expected_active_version_id: "active-new",
    target_version_id: "historic",
    reason: "合成修复原因",
  });
  expect(screen.getByLabelText("Prompt 正文")).toHaveAttribute("readonly");
});

it("固定评测只在显式点击后发生，并展示完整指纹及失败状态", async () => {
  vi.mocked(api.evaluatePromptVersion).mockResolvedValue({
    data: { ...evaluation, status: "failed", passed: false, error_key: "PROMPT_EVALUATION_FAILED" },
    message: "评测完成",
  });
  editor({ ...draft, latest_evaluation: null });
  expect(api.evaluatePromptVersion).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "执行固定评测" }));
  await waitFor(() =>
    expect(screen.getByText("失败原因：PROMPT_EVALUATION_FAILED")).toBeInTheDocument(),
  );
  expect(screen.getByText("f".repeat(64))).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "发布此版本" })).toBeDisabled();
});

it("停用确认传递已固定的目标状态，仅影响新任务", async () => {
  vi.mocked(api.setPromptDefinitionStatus).mockResolvedValue({
    data: { ...definition, runtime_status: "disabled" },
    message: "已停用",
  });
  editor();
  fireEvent.click(screen.getByRole("button", { name: "停用新任务" }));
  expect(screen.getByRole("dialog")).toHaveTextContent("只影响新的运行");
  fireEvent.click(screen.getByRole("button", { name: "确认操作" }));
  await waitFor(() =>
    expect(api.setPromptDefinitionStatus).toHaveBeenCalledWith("definition", {
      expected_active_version_id: "active-new",
      runtime_status: "disabled",
    }),
  );
});

it("代码场景退役后仅历史读取，不从空契约推断工具能力或继续写操作", () => {
  editor(draft, { ...definition, registered_contract: null, contract_sha256: null });
  expect(screen.getByLabelText("Prompt 正文")).toHaveAttribute("readonly");
  expect(screen.getByRole("button", { name: "执行固定评测" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "停用新任务" })).toBeDisabled();
  expect(screen.queryByRole("button", { name: "保存草稿" })).not.toBeInTheDocument();
  expect(api.evaluatePromptVersion).not.toHaveBeenCalled();
});
