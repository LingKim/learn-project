"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/features/auth/auth-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { AdminCaseDetail, QualityAdminQueueData } from "./api";
import { useCaseRefresh } from "./use-case-refresh";
import {
  adminCaseQueryOptions,
  adminCasesQueryOptions,
  overviewQueryOptions,
  removeQualityBody,
} from "./queries";
import {
  AdminActions,
  categoryLabels,
  Choice,
  GrantPanel,
  HistoryPanel,
  localTime,
  Panel,
  QueryProblem,
  ReplayPanel,
  resolutionLabels,
  statusLabels,
  TracePanel,
} from "./admin-panels";

// layout 负责后台外壳；此边界再阻止非管理员挂载业务查询组件。
function QualityAdminBoundary({ children }: { children: ReactNode }) {
  const { status, user } = useAuth();
  if (status === "loading") return <p role="status">正在核验管理员身份…</p>;
  if (status !== "authenticated" || user?.role !== "admin")
    return <p role="alert">仅管理员可以访问质量诊断。</p>;
  return <>{children}</>;
}
function Header({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <header className="mb-5 flex flex-wrap items-center justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold">{title}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{description}</p>
      </div>
      {children}
    </header>
  );
}
function CountRows({
  counts,
  labels = {},
}: {
  counts: Record<string, number>;
  labels?: Record<string, string>;
}) {
  return (
    <dl className="space-y-3 text-sm">
      {Object.entries(counts).map(([name, count]) => (
        <div key={name} className="flex justify-between gap-4 border-b border-border pb-3">
          <dt className="break-all">{labels[name] ?? name}</dt>
          <dd>{count}</dd>
        </div>
      ))}
      {!Object.keys(counts).length && <p className="text-muted-foreground">暂无记录</p>}
    </dl>
  );
}
function duration(seconds: number | null | undefined) {
  return seconds == null ? "暂无记录" : `${(seconds / 3600).toFixed(1)} 小时`;
}
export function QualityOverviewPage() {
  return (
    <QualityAdminBoundary>
      <OverviewContent />
    </QualityAdminBoundary>
  );
}
function OverviewContent() {
  const query = useQuery(overviewQueryOptions());
  const data = query.data;
  const total = data
    ? Object.values(data.counts_by_status).reduce((sum, count) => sum + count, 0)
    : 0;
  const daily = Object.entries(data?.daily_counts ?? {}).sort(([left], [right]) =>
    left.localeCompare(right),
  );
  const maxCount = Math.max(1, ...daily.map(([, count]) => count));
  return (
    <main className="mx-auto max-w-[1440px] p-5 md:p-8">
      <Header title="AI 质量诊断" description="从用户反馈发现重复问题，追踪处理效率与策略版本分布">
        <Button variant="outline" asChild>
          <Link href="/admin/ai-quality/cases">查看全部工单</Link>
        </Button>
      </Header>
      {query.error && <QueryProblem error={query.error} retry={() => void query.refetch()} />}
      {query.isPending && <p role="status">正在加载质量概览…</p>}
      {data && (
        <>
          <section
            className="mb-4 grid gap-4 rounded-lg border border-border bg-surface p-5 sm:grid-cols-2 xl:grid-cols-4"
            aria-label="质量指标"
          >
            {[
              ["收到反馈", total],
              ["待领取", data.counts_by_status.submitted ?? 0],
              ["已解决", data.counts_by_status.resolved ?? 0],
              ["首次响应 P95", duration(data.first_response_seconds.p95)],
            ].map(([label, value]) => (
              <div className="border-border xl:border-r last:xl:border-r-0" key={label}>
                <p className="text-xs text-muted-foreground">{label}</p>
                <p className="mt-2 text-2xl font-semibold">{value}</p>
              </div>
            ))}
          </section>
          <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_350px]">
            <div className="space-y-4">
              <Panel title="每日收到反馈">
                <div className="flex min-h-52 items-end gap-3 overflow-auto">
                  {daily.map(([day, count]) => (
                    <div
                      key={day}
                      className="flex min-w-16 flex-1 flex-col items-center gap-2 text-xs"
                    >
                      <span>{count}</span>
                      <div
                        className="w-6 rounded-t bg-primary"
                        style={{ height: `${(count / maxCount) * 140}px` }}
                      />
                      <span className="text-muted-foreground">{day}</span>
                    </div>
                  ))}
                  {!daily.length && (
                    <p className="self-center text-sm text-muted-foreground">暂无每日反馈记录</p>
                  )}
                </div>
              </Panel>
              <Panel title="问题类型分布">
                <CountRows counts={data.counts_by_category} labels={categoryLabels} />
              </Panel>
              <Panel title="策略版本分布">
                <CountRows counts={data.counts_by_strategy} />
              </Panel>
            </div>
            <aside className="space-y-4">
              <Panel title="处理队列">
                <CountRows counts={data.counts_by_status} labels={statusLabels} />
              </Panel>
              <Panel title="处理时长">
                <dl className="space-y-4 text-sm">
                  {(
                    [
                      ["首次响应", data.first_response_seconds],
                      ["解决", data.resolution_seconds],
                      ["积压", data.backlog_seconds],
                    ] as const
                  ).map(([label, values]) => (
                    <div key={label}>
                      <dt>{label}</dt>
                      <dd className="mt-1 text-muted-foreground">
                        P50 {duration(values.p50)} / P95 {duration(values.p95)}
                      </dd>
                    </div>
                  ))}
                </dl>
              </Panel>
              <Panel title="业务类型">
                <CountRows
                  counts={data.counts_by_source}
                  labels={{ learning_turn: "学习室 · 资料回答" }}
                />
              </Panel>
              <Panel title="错误码（脱敏统计）" className="bg-[#fff7d8]">
                <CountRows counts={data.error_counts} />
              </Panel>
            </aside>
          </div>
        </>
      )}
    </main>
  );
}

type QueueFilters = NonNullable<QualityAdminQueueData["query"]>;
export function QualityQueuePage() {
  return (
    <QualityAdminBoundary>
      <QueueContent />
    </QualityAdminBoundary>
  );
}
function QueueContent() {
  const { user } = useAuth();
  const [filters, setFilters] = useState<QueueFilters>({ page: 1, page_size: 20, sort: "oldest" });
  const query = useQuery(adminCasesQueryOptions(filters));
  const change = (next: Partial<QueueFilters>) =>
    setFilters((current) => ({ ...current, ...next, page: 1 }));
  return (
    <main className="mx-auto max-w-[1440px] p-5 md:p-8">
      <Header title="质量工单" description="按结构化字段处理反馈，正文只在有效授权的工单详情中显示">
        <Button
          variant="outline"
          onClick={() =>
            change({ assignee_id: filters.assignee_id === user?.id ? null : user?.id })
          }
        >
          {filters.assignee_id === user?.id ? "查看全部负责人" : "只看我负责"}
        </Button>
      </Header>
      <div className="mb-4 flex flex-wrap gap-2" aria-label="工单状态筛选">
        <Button
          variant={!filters.status ? "brand" : "ghost"}
          onClick={() => change({ status: null })}
        >
          全部
        </Button>
        {Object.entries(statusLabels).map(([status, label]) => (
          <Button
            key={status}
            variant={filters.status === status ? "brand" : "ghost"}
            onClick={() => change({ status: status as AdminCaseDetail["status"] })}
          >
            {label}
          </Button>
        ))}
      </div>
      <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Choice
          label="问题类型"
          value={filters.category ?? "all"}
          choices={{ all: "全部问题类型", ...categoryLabels }}
          onChange={(value) =>
            change({ category: value === "all" ? null : (value as AdminCaseDetail["category"]) })
          }
        />
        <Choice
          label="业务类型"
          value={filters.source_type ?? "all"}
          choices={{ all: "全部业务", learning_turn: "学习室 · 资料回答" }}
          onChange={(value) => change({ source_type: value === "all" ? null : "learning_turn" })}
        />
        <div className="space-y-2">
          <Label htmlFor="quality-strategy">策略版本</Label>
          <Input
            id="quality-strategy"
            value={filters.strategy_version ?? ""}
            onChange={(event) => change({ strategy_version: event.target.value || null })}
            placeholder="完整策略版本"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="quality-owner">负责人 UUID</Label>
          <Input
            id="quality-owner"
            value={filters.assignee_id ?? ""}
            onChange={(event) => change({ assignee_id: event.target.value || null })}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="quality-after">提交起始日期</Label>
          <Input
            id="quality-after"
            type="date"
            value={filters.created_after?.slice(0, 10) ?? ""}
            onChange={(event) =>
              change({
                created_after: event.target.value ? `${event.target.value}T00:00:00Z` : null,
              })
            }
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="quality-before">提交截止日期</Label>
          <Input
            id="quality-before"
            type="date"
            value={filters.created_before?.slice(0, 10) ?? ""}
            onChange={(event) =>
              change({
                created_before: event.target.value ? `${event.target.value}T23:59:59.999Z` : null,
              })
            }
          />
        </div>
        <Choice
          label="排序"
          value={filters.sort ?? "oldest"}
          choices={{ oldest: "最久未处理", updated: "最近更新", newest: "最新提交" }}
          onChange={(value) => change({ sort: value as QueueFilters["sort"] })}
        />
      </div>
      {query.error && <QueryProblem error={query.error} retry={() => void query.refetch()} />}
      {query.isPending && <p role="status">正在加载工单…</p>}
      {query.data && (
        <section className="min-h-96 overflow-hidden rounded-lg border border-border bg-surface">
          <Table>
            <TableHeader className="bg-muted">
              <TableRow>
                {[
                  "工单号",
                  "用户",
                  "问题类型",
                  "业务场景",
                  "状态",
                  "策略版本",
                  "负责人",
                  "提交 / 最近更新",
                  "操作",
                ].map((text) => (
                  <TableHead key={text}>{text}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.data.data.map((item) => (
                <TableRow key={item.id}>
                  <TableCell>{item.case_number}</TableCell>
                  <TableCell className="max-w-36 break-all">{item.user_id}</TableCell>
                  <TableCell>{categoryLabels[item.category]}</TableCell>
                  <TableCell>学习室 · 资料回答</TableCell>
                  <TableCell>
                    <Badge variant="warm">{statusLabels[item.status]}</Badge>
                  </TableCell>
                  <TableCell className="max-w-52 break-all">{item.strategy_version}</TableCell>
                  <TableCell className="max-w-36 break-all">
                    {item.assignee_id ?? "未领取"}
                  </TableCell>
                  <TableCell>
                    {localTime(item.created_at)}
                    <br />
                    {localTime(item.updated_at)}
                  </TableCell>
                  <TableCell>
                    <Button variant="ghost" size="sm" asChild>
                      <Link href={`/admin/ai-quality/cases/${item.id}`}>
                        {item.assignee_id ? "查看" : "领取 / 查看"}
                      </Link>
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {!query.data.data.length && (
            <p className="p-8 text-center text-sm text-muted-foreground">暂无符合筛选条件的工单</p>
          )}
          <footer className="flex flex-wrap items-center justify-between gap-3 p-4 text-xs text-muted-foreground">
            <p>列表仅展示脱敏结构化字段，不检索用户正文。共 {query.data.meta.total} 条</p>
            <div className="flex items-center gap-3">
              <Button
                variant="outline"
                size="sm"
                disabled={query.data.meta.page <= 1 || query.isFetching}
                onClick={() =>
                  setFilters((current) => ({ ...current, page: (current.page ?? 1) - 1 }))
                }
              >
                上一页
              </Button>
              <span>
                {query.data.meta.page} / {Math.max(1, query.data.meta.total_pages)}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={query.data.meta.page >= query.data.meta.total_pages || query.isFetching}
                onClick={() =>
                  setFilters((current) => ({ ...current, page: (current.page ?? 1) + 1 }))
                }
              >
                下一页
              </Button>
            </div>
          </footer>
        </section>
      )}
    </main>
  );
}

export function QualityAdminDetailPage({ id }: { id: string }) {
  const { user } = useAuth();
  return (
    <QualityAdminBoundary>
      <DetailContent key={`${user?.id}:${id}`} id={id} />
    </QualityAdminBoundary>
  );
}
// 本地后备只保留可操作的元数据；清缓存后不能以另一份 React state 留住事件正文或结论。
function metadataOnly(detail: AdminCaseDetail): AdminCaseDetail {
  return {
    ...detail,
    resolution_summary: null,
    events: detail.events.map((event) => ({ ...event, content: null })),
  };
}
function DetailContent({ id }: { id: string }) {
  const { user } = useAuth();
  const client = useQueryClient();
  const [keyVersion, setKeyVersion] = useState(0);
  const [tab, setTab] = useState("overview");
  const [busy, setBusy] = useState(false);
  const [metadata, setMetadata] = useState<AdminCaseDetail | null>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const lifetime = useCaseRefresh("admin", id, keyVersion);
  const query = useQuery(adminCaseQueryOptions(client, id, keyVersion, lifetime.revision));
  const liveDetail = query.data;
  const detail =
    busy || !liveDetail ? (metadata ?? (liveDetail ? metadataOnly(liveDetail) : null)) : liveDetail;
  // 版本来自后端；读取代次用于重新挂载被敏感缓存清除器移除的 Query observer。
  useEffect(() => {
    if (liveDetail) {
      setMetadata(metadataOnly(liveDetail));
      if (liveDetail.version !== keyVersion) setKeyVersion(liveDetail.version);
    }
  }, [liveDetail, keyVersion]);
  async function refresh() {
    if (!mounted.current) return;
    lifetime.busy.current = true;
    setBusy(true);
    await removeQualityBody(client, id);
    // 旧页的异步续行不得再清除或重取同一工单在新页的缓存。
    if (!mounted.current) return;
    lifetime.busy.current = false;
    setBusy(false);
    lifetime.refresh();
  }
  return (
    <main className="mx-auto max-w-[1440px] p-5 md:p-8">
      <Link className="text-sm text-muted-foreground" href="/admin/ai-quality/cases">
        ← 质量工单
      </Link>
      <div className="mt-4">
        <Header
          title={detail ? `${categoryLabels[detail.category]} · 链路诊断` : "质量工单详情"}
          description={
            detail
              ? `${detail.case_number} · 提交 ${localTime(detail.created_at)} · 版本 ${detail.version}`
              : "按工单边界读取诊断信息"
          }
        >
          <Button variant="outline" onClick={() => void refresh()} disabled={busy}>
            刷新工单
          </Button>
        </Header>
      </div>
      {query.error && <QueryProblem error={query.error} retry={() => void refresh()} />}
      {(query.isPending || busy) && <p role="status">正在刷新工单与授权状态…</p>}
      {detail && (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <Badge variant="warm">{statusLabels[detail.status]}</Badge>
            <span className="break-all text-xs text-muted-foreground">
              用户 {detail.user_id} · 负责人 {detail.assignee_id ?? "未领取"}
            </span>
          </div>
          <nav
            className="mb-4 flex flex-wrap gap-2 border-b border-border pb-3"
            aria-label="工单详情视图"
          >
            {Object.entries({
              overview: "工单概览",
              trace: "链路诊断",
              replay: "回放对比",
              history: "处理记录",
            }).map(([name, label]) => (
              <Button
                key={name}
                variant={tab === name ? "brand" : "ghost"}
                aria-current={tab === name ? "page" : undefined}
                onClick={() => setTab(name)}
              >
                {label}
              </Button>
            ))}
          </nav>
          <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
            <div className="space-y-4">
              {tab === "overview" && (
                <>
                  <Panel title="工单元数据">
                    <dl className="grid gap-4 text-sm sm:grid-cols-2">
                      <div>
                        <dt>问题类型</dt>
                        <dd>{categoryLabels[detail.category]}</dd>
                      </div>
                      <div>
                        <dt>业务场景</dt>
                        <dd>学习室 · 资料回答</dd>
                      </div>
                      <div>
                        <dt>来源 ID</dt>
                        <dd className="break-all">{detail.source_id}</dd>
                      </div>
                      <div>
                        <dt>Trace ID</dt>
                        <dd className="break-all">{detail.trace_id}</dd>
                      </div>
                      <div>
                        <dt>策略版本</dt>
                        <dd className="break-all">{detail.strategy_version}</dd>
                      </div>
                      <div>
                        <dt>最近更新</dt>
                        <dd>{localTime(detail.updated_at)}</dd>
                      </div>
                    </dl>
                    {detail.source_error && (
                      <p className="mt-4" role="alert">
                        来源不可用：{detail.source_error}
                      </p>
                    )}
                    <p className="mt-4 text-xs text-muted-foreground">
                      用户陈述与期望结果通过右侧有效授权逐字段读取。
                    </p>
                  </Panel>
                  {detail.resolution_summary && (
                    <Panel title="解决结论">
                      <p className="text-xs text-muted-foreground">
                        归因：
                        {detail.resolution_code
                          ? resolutionLabels[detail.resolution_code]
                          : "未归因"}
                      </p>
                      <p className="mt-2 whitespace-pre-wrap text-sm">
                        {detail.resolution_summary}
                      </p>
                    </Panel>
                  )}
                </>
              )}
              {tab === "trace" && <TracePanel detail={detail} />}
              {tab === "replay" && <ReplayPanel detail={detail} />}
              {tab === "history" && <HistoryPanel detail={detail} />}
            </div>
            <aside className="space-y-4">
              <GrantPanel detail={detail} busy={busy || !liveDetail} />
              <AdminActions
                key={`${detail.id}:${user!.id}`}
                detail={detail}
                actorId={user!.id}
                refreshing={busy || !liveDetail}
                onStart={() => {
                  lifetime.busy.current = true;
                  setBusy(true);
                }}
                onFinished={refresh}
              />
            </aside>
          </div>
        </>
      )}
    </main>
  );
}
