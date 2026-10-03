import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as api from "./api";
import type { AdminCaseDetail, GrantView } from "./api";
import { QualityAdminDetailPage, QualityOverviewPage, QualityQueuePage } from "./admin-pages";
import { AdminActions, GrantPanel, TracePanel } from "./admin-panels";
import { qualityKeys } from "./queries";

const auth = vi.hoisted(() => ({ status: "authenticated", user: { id: "admin", role: "admin" } }));
vi.mock("@/features/auth/auth-provider", () => ({ useAuth: () => auth }));
vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  getOverview: vi.fn(),
  listAdminCases: vi.fn(),
  getAdminCase: vi.fn(),
  getSnapshot: vi.fn(),
  assignCase: vi.fn(),
  requestAccess: vi.fn(),
  replayCase: vi.fn(),
  addAdminMessage: vi.fn(),
  transitionCase: vi.fn(),
}));

const grant: GrantView = {
  id: "grant",
  version: 2,
  status: "active",
  fields: ["query", "final_output"],
  chunk_ids: [],
  reason: "仅诊断本次请求",
  requester_id: null,
  expires_at: "2099-10-03T00:00:00Z",
  confirmed_at: null,
  revoked_at: null,
};
function fixture(): AdminCaseDetail {
  return {
    id: "case",
    case_number: "Q-1",
    user_id: "owner",
    source_type: "learning_turn",
    source_id: "turn",
    trace_id: "trace",
    category: "wrong_answer",
    status: "triaging",
    version: 3,
    strategy_version: "fts-v1",
    assignee_id: null,
    created_at: "2026-10-03T00:00:00Z",
    updated_at: "2026-10-03T00:00:00Z",
    resolved_at: null,
    closed_at: null,
    resolution_code: null,
    resolution_summary: null,
    trace: null,
    source_error: "TRACE_INCOMPLETE",
    grants: [grant],
    events: [],
    replays: [],
    audits: [],
  };
}
function setup(node: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
  return client;
}
beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
    configurable: true,
    value: vi.fn(),
  });
  auth.status = "authenticated";
  auth.user.role = "admin";
  vi.mocked(api.getAdminCase).mockResolvedValue(fixture());
  vi.mocked(api.getSnapshot).mockResolvedValue({
    case_id: "case",
    grant_id: "grant",
    grant_version: 2,
    expires_at: grant.expires_at,
    values: { query: "授权问题正文" },
    description: "用户陈述",
    expected_result: null,
  });
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

async function choose(label: string, option: string) {
  fireEvent.keyDown(screen.getByRole("combobox", { name: label }), { key: "Enter" });
  fireEvent.click(await screen.findByRole("option", { name: option }));
}
describe("管理员质量视图", () => {
  it("普通用户拒绝三个页面且不发后台查询", () => {
    auth.user.role = "user";
    setup(
      <>
        <QualityOverviewPage />
        <QualityQueuePage />
        <QualityAdminDetailPage id="case" />
      </>,
    );
    expect(screen.getAllByRole("alert")).toHaveLength(3);
    expect(api.getOverview).not.toHaveBeenCalled();
    expect(api.listAdminCases).not.toHaveBeenCalled();
    expect(api.getAdminCase).not.toHaveBeenCalled();
    expect(api.getSnapshot).not.toHaveBeenCalled();
  });
  it("待认证不挂载诊断查询", () => {
    auth.status = "loading";
    setup(<QualityAdminDetailPage id="case" />);
    expect(screen.getByRole("status")).toHaveTextContent("核验管理员");
    expect(api.getAdminCase).not.toHaveBeenCalled();
  });
  it("非有效授权不请求正文", () => {
    const detail = fixture();
    detail.grants = [
      { ...grant, status: "revoked" },
      { ...grant, id: "expired", expires_at: "2020-01-01T00:00:00Z" },
      { ...grant, id: "pending", status: "pending" },
    ];
    setup(<GrantPanel detail={detail} busy={false} />);
    expect(screen.queryByRole("button", { name: "读取已选择的授权字段" })).not.toBeInTheDocument();
    expect(api.getSnapshot).not.toHaveBeenCalled();
  });
  it("正文按明确选择的字段读取，不写浏览器持久存储", async () => {
    const local = vi.spyOn(Storage.prototype, "setItem");
    setup(<GrantPanel detail={fixture()} busy={false} />);
    expect(api.getSnapshot).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("checkbox", { name: "本次 Query" }));
    fireEvent.click(screen.getByRole("button", { name: "读取已选择的授权字段" }));
    expect(await screen.findByText("授权问题正文")).toBeInTheDocument();
    expect(api.getSnapshot).toHaveBeenCalledWith(
      "case",
      { grant_id: "grant", expected_grant_version: 2, fields: ["query"] },
      expect.any(AbortSignal),
    );
    expect(local).not.toHaveBeenCalled();
  });
  it("授权关闭时不展示正文或启动读取", () => {
    const detail = { ...fixture(), status: "closed" as const };
    setup(<GrantPanel detail={detail} busy={false} />);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(api.getSnapshot).not.toHaveBeenCalled();
  });
  it("处置先清正文，结束后重新加载详情并使用真实版本键", async () => {
    let current = fixture();
    vi.mocked(api.getAdminCase).mockImplementation(async () => current);
    let finish: (() => void) | undefined;
    vi.mocked(api.assignCase).mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = () => {
            current = { ...current, version: 4, assignee_id: "admin" };
            resolve({ data: current, message: "成功" });
          };
        }),
    );
    const client = setup(<QualityAdminDetailPage id="case" />);
    await screen.findByText("负责人 UUID");
    fireEvent.click(await screen.findByRole("checkbox", { name: "本次 Query" }));
    fireEvent.click(screen.getByRole("button", { name: "读取已选择的授权字段" }));
    await screen.findByText("授权问题正文");
    fireEvent.click(screen.getByRole("button", { name: "提交操作" }));
    await waitFor(() =>
      expect(api.assignCase).toHaveBeenCalledWith("case", {
        expected_version: 3,
        assignee_id: "admin",
      }),
    );
    expect(screen.queryByText("授权问题正文")).not.toBeInTheDocument();
    await act(async () => finish?.());
    await waitFor(() => expect(screen.getByText(/版本 4/)).toBeInTheDocument());
    await waitFor(() =>
      expect(
        client
          .getQueryCache()
          .findAll({ queryKey: qualityKeys.detail("admin", "case", 4) })
          .some((query) => (query.state.data as AdminCaseDetail | undefined)?.version === 4),
      ).toBe(true),
    );
    expect(
      client.getQueryCache().findAll({ queryKey: qualityKeys.detail("admin", "case", 3) }),
    ).toHaveLength(0);
  });
  it("缺失阶段与耗时不能被补成零耗时成功", () => {
    const detail = fixture();
    detail.trace = {
      trace_id: "trace",
      strategy_version: "fts",
      stages: [{ stage: "keyword", candidates: [], elapsed_ms: null }],
      final_chunk_ids: [],
      occurred_at: detail.created_at,
      expires_at: grant.expires_at,
      error_code: null,
      prompt_manifest: {},
      model_parameters: {},
    };
    setup(<TracePanel detail={detail} />);
    expect(screen.getAllByText("FTS")).toHaveLength(2);
    expect(screen.getAllByText("阶段缺失")).toHaveLength(5);
    expect(screen.queryByText("0 ms")).not.toBeInTheDocument();
    expect(screen.getAllByText("耗时未记录")).toHaveLength(6);
  });
  it("概览不伪造每日已解决曲线与百分比", async () => {
    vi.mocked(api.getOverview).mockResolvedValue({
      counts_by_status: {},
      counts_by_category: {},
      counts_by_source: {},
      counts_by_strategy: {},
      daily_counts: {},
      first_response_seconds: { p50: null, p95: null },
      resolution_seconds: {},
      backlog_seconds: {},
      error_counts: {},
    });
    setup(<QualityOverviewPage />);
    await screen.findByText("每日收到反馈");
    expect(screen.getByText("暂无每日反馈记录")).toBeInTheDocument();
    expect(screen.queryByText("82%")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });
  it("追加授权提交明确用途、去重指定片段与有效期", async () => {
    vi.mocked(api.requestAccess).mockResolvedValue({ data: fixture(), message: "成功" });
    const done = vi.fn(async () => {});
    setup(<AdminActions detail={fixture()} actorId="admin" onStart={() => {}} onFinished={done} />);
    await choose("操作", "请求候选片段追加授权");
    expect(screen.getByRole("button", { name: "提交操作" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("诊断用途"), {
      target: { value: "核对候选片段与问题的关联" },
    });
    fireEvent.change(screen.getByLabelText("指定候选 Chunk IDs（必填）"), {
      target: { value: "chunk-a, chunk-a\nchunk-b" },
    });
    fireEvent.change(screen.getByLabelText("有效天数（1–30）"), { target: { value: "7" } });
    fireEvent.click(screen.getByRole("button", { name: "提交操作" }));
    await waitFor(() =>
      expect(api.requestAccess).toHaveBeenCalledWith("case", {
        expected_version: 3,
        reason: "核对候选片段与问题的关联",
        chunk_ids: ["chunk-a", "chunk-b"],
        duration_days: 7,
      }),
    );
    await waitFor(() => expect(done).toHaveBeenCalled());
  });
  it("内部备注提交admin可见范围并携带版本", async () => {
    vi.mocked(api.addAdminMessage).mockResolvedValue({ data: fixture(), message: "成功" });
    setup(
      <AdminActions
        detail={fixture()}
        actorId="admin"
        onStart={() => {}}
        onFinished={async () => {}}
      />,
    );
    await choose("操作", "回复 / 内部备注");
    await choose("可见范围", "内部备注（仅管理员）");
    fireEvent.change(screen.getByLabelText("内部备注"), {
      target: { value: "仅记录判断，等待用户补充" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交操作" }));
    await waitFor(() =>
      expect(api.addAdminMessage).toHaveBeenCalledWith("case", {
        expected_version: 3,
        content: "仅记录判断，等待用户补充",
        visibility: "admin",
      }),
    );
  });
  it("解决工单要求公开结论和归因", async () => {
    vi.mocked(api.transitionCase).mockResolvedValue({ data: fixture(), message: "成功" });
    setup(
      <AdminActions
        detail={fixture()}
        actorId="admin"
        onStart={() => {}}
        onFinished={async () => {}}
      />,
    );
    await choose("操作", "状态与解决归因");
    await choose("目标状态", "已解决");
    expect(screen.getByRole("button", { name: "提交操作" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("公开结论（必填）"), {
      target: { value: "当前未复现，保留诊断记录" },
    });
    await choose("解决归因", "未复现");
    fireEvent.click(screen.getByRole("button", { name: "提交操作" }));
    await waitFor(() =>
      expect(api.transitionCase).toHaveBeenCalledWith("case", {
        expected_version: 3,
        status: "resolved",
        resolution_code: "not_reproduced",
        resolution_summary: "当前未复现，保留诊断记录",
      }),
    );
  });
  it("回放提交有效授权版本与记录候选模式", async () => {
    vi.mocked(api.replayCase).mockResolvedValue({ data: fixture(), message: "成功" });
    setup(
      <AdminActions
        detail={fixture()}
        actorId="admin"
        onStart={() => {}}
        onFinished={async () => {}}
      />,
    );
    await choose("操作", "运行记录候选离线对照");
    expect(screen.getByRole("button", { name: "提交操作" })).toBeDisabled();
    await choose("使用授权", "v2 · 本次 Query、最终回答");
    await choose("对照模式", "FTS-only");
    fireEvent.click(screen.getByRole("button", { name: "提交操作" }));
    await waitFor(() =>
      expect(api.replayCase).toHaveBeenCalledWith("case", {
        expected_version: 3,
        grant_id: "grant",
        expected_grant_version: 2,
        mode: "fts_only",
        target_chunk_ids: [],
      }),
    );
  });
  it("已挂载详情授权到期后丢弃正文并重新读取元数据", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-03T00:00:00Z"));
    const expiry = "2026-10-03T00:00:05Z";
    let current = { ...fixture(), grants: [{ ...grant, expires_at: expiry }] };
    vi.mocked(api.getAdminCase).mockImplementation(async () => current);
    vi.mocked(api.getSnapshot).mockResolvedValue({
      case_id: "case",
      grant_id: "grant",
      grant_version: 2,
      expires_at: expiry,
      values: { query: "到期必须清除的正文" },
    });
    setup(<QualityAdminDetailPage id="case" />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    fireEvent.click(screen.getByRole("checkbox", { name: "本次 Query" }));
    fireEvent.click(screen.getByRole("button", { name: "读取已选择的授权字段" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    expect(screen.getByText("到期必须清除的正文")).toBeInTheDocument();
    current = { ...current, grants: [{ ...current.grants[0], status: "expired" }] };
    const before = vi.mocked(api.getAdminCase).mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(screen.queryByText("到期必须清除的正文")).not.toBeInTheDocument();
    expect(screen.getByText(/已到期/)).toBeInTheDocument();
    expect(vi.mocked(api.getAdminCase).mock.calls.length).toBeGreaterThan(before);
  });
  it("延迟失败后保持备注草稿和局部错误，并从最新工单版本重试", async () => {
    let current = fixture();
    current.events = [
      {
        id: "event",
        action: "internal_note",
        visibility: "admin",
        actor_id: "admin",
        version: 3,
        content: "原事件敏感正文",
        created_at: current.created_at,
      },
    ];
    vi.mocked(api.getAdminCase).mockImplementation(async () => current);
    let reject: ((cause: Error) => void) | undefined;
    vi.mocked(api.addAdminMessage).mockImplementationOnce(
      () =>
        new Promise((_resolve, rejectRequest) => {
          reject = rejectRequest;
        }),
    );
    vi.mocked(api.addAdminMessage).mockResolvedValue({
      data: { ...current, version: 5 },
      message: "成功",
    });
    setup(<QualityAdminDetailPage id="case" />);
    await screen.findByRole("checkbox", { name: "本次 Query" });
    fireEvent.click(screen.getByRole("button", { name: "处理记录" }));
    expect(screen.getByText("原事件敏感正文")).toBeInTheDocument();
    await choose("操作", "回复 / 内部备注");
    await choose("可见范围", "内部备注（仅管理员）");
    fireEvent.change(screen.getByLabelText("内部备注"), {
      target: { value: "尚未提交的判断草稿" },
    });
    const textarea = screen.getByLabelText("内部备注");
    fireEvent.click(screen.getByRole("button", { name: "提交操作" }));
    await waitFor(() => expect(api.addAdminMessage).toHaveBeenCalledTimes(1));
    expect(screen.getByLabelText("内部备注")).toBe(textarea);
    expect(textarea).toHaveValue("尚未提交的判断草稿");
    expect(textarea).toBeDisabled();
    expect(screen.queryByText("原事件敏感正文")).not.toBeInTheDocument();
    current = { ...current, version: 4, events: [] };
    await act(async () => reject?.(new Error("版本冲突，请重试")));
    await waitFor(() => expect(screen.getByLabelText("内部备注")).not.toBeDisabled());
    expect(screen.getByLabelText("内部备注")).toBe(textarea);
    expect(textarea).toHaveValue("尚未提交的判断草稿");
    expect(screen.getByRole("alert")).toHaveTextContent("版本冲突，请重试");
    fireEvent.click(screen.getByRole("button", { name: "提交操作" }));
    await waitFor(() =>
      expect(api.addAdminMessage).toHaveBeenLastCalledWith("case", {
        expected_version: 4,
        content: "尚未提交的判断草稿",
        visibility: "admin",
      }),
    );
  });
  it("旧页面卸载后的处置响应不能清掉重新打开工单的正文缓存", async () => {
    vi.mocked(api.getAdminCase).mockImplementation(async (id) => ({ ...fixture(), id }));
    let complete: (() => void) | undefined;
    vi.mocked(api.assignCase).mockImplementation(
      () =>
        new Promise((resolve) => {
          complete = () => resolve({ data: { ...fixture(), version: 4 }, message: "完成" });
        }),
    );
    vi.mocked(api.getSnapshot).mockResolvedValue({
      case_id: "case",
      grant_id: "grant",
      grant_version: 2,
      expires_at: grant.expires_at,
      values: { query: "重新打开工单的正文" },
    });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const page = (id: string) => (
      <QueryClientProvider client={client}>
        <QualityAdminDetailPage id={id} />
      </QueryClientProvider>
    );
    const view = render(page("case"));
    await screen.findByRole("checkbox", { name: "本次 Query" });
    fireEvent.click(screen.getByRole("button", { name: "提交操作" }));
    await waitFor(() => expect(api.assignCase).toHaveBeenCalledTimes(1));
    view.rerender(page("other"));
    await screen.findByRole("checkbox", { name: "本次 Query" });
    view.rerender(page("case"));
    fireEvent.click(await screen.findByRole("checkbox", { name: "本次 Query" }));
    fireEvent.click(screen.getByRole("button", { name: "读取已选择的授权字段" }));
    await screen.findByText("重新打开工单的正文");
    const calls = vi.mocked(api.getAdminCase).mock.calls.length;
    await act(async () => complete?.());
    expect(screen.getByText("重新打开工单的正文")).toBeInTheDocument();
    expect(
      client.getQueryData(qualityKeys.snapshot("case", 3, "grant", 2, ["query"])),
    ).toMatchObject({ values: { query: "重新打开工单的正文" } });
    expect(vi.mocked(api.getAdminCase).mock.calls.length).toBe(calls);
  });
  it("后台事件动作和解决归因显示中文标签", async () => {
    const detail = {
      ...fixture(),
      resolution_code: "fts_filter" as const,
      resolution_summary: "记录排序已核对",
      events: [
        {
          id: "e",
          action: "case_resolved",
          visibility: "user" as const,
          actor_id: "admin",
          version: 3,
          content: null,
          created_at: fixture().created_at,
        },
      ],
    };
    vi.mocked(api.getAdminCase).mockResolvedValue(detail);
    setup(<QualityAdminDetailPage id="case" />);
    await screen.findByText("归因：FTS 过滤");
    fireEvent.click(screen.getByRole("button", { name: "处理记录" }));
    expect(screen.getByText(/工单已解决 · 公开/)).toBeInTheDocument();
    expect(screen.queryByText(/case_resolved/)).not.toBeInTheDocument();
  });
});
