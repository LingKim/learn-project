"use client";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowLeft, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableHeader,
  TableHead,
  TableBody,
  TableCell,
  TableRow,
} from "@/components/ui/table";
import { useAuth } from "@/features/auth/auth-provider";
import { ContentShell } from "@/features/file-management/content-shell";
import {
  caseQueryOptions,
  casesQueryOptions,
  addMessageMutationOptions,
  closeCaseMutationOptions,
  withdrawCaseMutationOptions,
  decideGrantMutationOptions,
  revokeGrantMutationOptions,
} from "./queries";
import type { CaseView, UserCaseDetail, GrantView } from "./api";
import {
  categories,
  statuses,
  grantStatuses,
  grantFields,
  dateLabel,
  Panel,
  ErrorNotice,
  StatusBadge,
  EventTimeline,
} from "./common";
import { useCaseRefresh } from "./use-case-refresh";
const selectClass = "min-h-10 rounded-md border border-border bg-surface px-3 text-sm";

export function MyQualityCasesPage() {
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<CaseView["status"] | "">("");
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const cases = useQuery({
    ...casesQueryOptions({ page, page_size: 20, ...(status ? { status } : {}) }),
    enabled: user?.role === "user",
  });
  const items = cases.data?.data ?? [];
  const shown = items.filter(
    (item) =>
      (!category || item.category === category) &&
      item.case_number.toLowerCase().includes(search.trim().toLowerCase()),
  );
  const statistics = [
    ["全部反馈", cases.data?.meta.total ?? "—"],
    ["本页待处理", items.filter((item) => item.status === "submitted").length],
    [
      "本页处理中",
      items.filter((item) => ["triaging", "investigating", "waiting_user"].includes(item.status))
        .length,
    ],
    ["本页已解决", items.filter((item) => item.status === "resolved").length],
  ];
  return (
    <ContentShell>
      <div className="mx-auto grid w-full max-w-[1440px] gap-4 p-5 lg:p-10">
        <header className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold">我的反馈</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              查看问题处理进度、补充说明和管理员回复
            </p>
          </div>
          <Button asChild variant="outline">
            <Link href="/learning">
              <ArrowLeft />
              返回学习室
            </Link>
          </Button>
        </header>
        {user?.role !== "user" ? (
          <p role="alert">请使用本人学习账号查看反馈。</p>
        ) : (
          <>
            <div className="grid grid-cols-2 rounded-[10px] border border-border bg-surface p-2 sm:grid-cols-4">
              {statistics.map(([label, value]) => (
                <div key={label} className="border-border p-4 sm:not-last:border-r">
                  <p className="text-xs text-muted-foreground">{label}</p>
                  <p className="mt-2 text-2xl font-semibold">{value}</p>
                </div>
              ))}
            </div>
            <div className="grid gap-2 md:grid-cols-[1fr_180px_200px]">
              <Input
                aria-label="筛选本页工单号"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="筛选本页工单号"
                className="h-10 bg-surface"
              />
              <select
                aria-label="反馈状态"
                className={selectClass}
                value={status}
                onChange={(event) => {
                  setStatus(event.target.value as CaseView["status"] | "");
                  setPage(1);
                }}
              >
                <option value="">状态：全部</option>
                {Object.entries(statuses).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <select
                aria-label="本页问题类型"
                className={selectClass}
                value={category}
                onChange={(event) => setCategory(event.target.value)}
              >
                <option value="">本页问题类型：全部</option>
                {Object.entries(categories).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            {cases.error && <ErrorNotice error={cases.error} />}
            <section className="min-h-[540px] overflow-hidden rounded-[10px] border border-border bg-surface">
              <Table>
                <TableHeader className="bg-muted">
                  <TableRow>
                    {["工单号", "问题类型", "关联内容", "状态", "最近更新", "操作"].map((label) => (
                      <TableHead key={label}>{label}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {shown.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>{item.case_number}</TableCell>
                      <TableCell>{categories[item.category]}</TableCell>
                      <TableCell>学习室 · 资料问答</TableCell>
                      <TableCell>
                        <StatusBadge status={item.status} />
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {dateLabel(item.updated_at)}
                      </TableCell>
                      <TableCell>
                        <Link
                          className="text-sky-800 underline-offset-4 hover:underline"
                          href={`/ai-quality/${item.id}`}
                        >
                          {item.status === "waiting_user" ? "补充" : "查看"}
                        </Link>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {cases.isPending && (
                <p role="status" className="p-6 text-sm text-muted-foreground">
                  正在加载反馈…
                </p>
              )}
              {!cases.isPending && !cases.error && !shown.length && (
                <p className="p-6 text-sm text-muted-foreground">暂无符合条件的反馈</p>
              )}
              <div className="flex flex-wrap items-center justify-between gap-3 p-4 text-xs text-muted-foreground">
                <span>
                  共 {cases.data?.meta.total ?? 0} 条反馈 · 第 {page} 页
                </span>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => setPage((value) => value - 1)}
                  >
                    上一页
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!cases.data || page >= cases.data.meta.total_pages}
                    onClick={() => setPage((value) => value + 1)}
                  >
                    下一页
                  </Button>
                </div>
              </div>
            </section>
          </>
        )}
      </div>
    </ContentShell>
  );
}
export function MyQualityCasePage({ id }: { id: string }) {
  const { user } = useAuth();
  return (
    <ContentShell>
      <MyQualityCaseContent key={`${user?.id}:${id}`} id={id} />
    </ContentShell>
  );
}
function MyQualityCaseContent({ id }: { id: string }) {
  const { user } = useAuth();
  const client = useQueryClient();
  const [version, setVersion] = useState(0);
  const active = useRef(true);
  const scope = useCaseRefresh("user", id, version);
  const options = caseQueryOptions(client, id, version, scope.revision);
  const detail = useQuery({
    ...options,
    enabled: user?.role === "user",
  });
  const add = useMutation(addMessageMutationOptions(client, () => active.current));
  const close = useMutation(closeCaseMutationOptions(client, () => active.current));
  const withdraw = useMutation(withdrawCaseMutationOptions(client, () => active.current));
  const decision = useMutation(decideGrantMutationOptions(client, () => active.current));
  const revoke = useMutation(revokeGrantMutationOptions(client, () => active.current));
  const [message, setMessage] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [working, setWorking] = useState(false);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);
  async function act(action: () => Promise<{ data: UserCaseDetail }>, clearMessage = false) {
    if (scope.busy.current) return;
    scope.busy.current = true;
    setWorking(true);
    setError(null);
    try {
      const result = await action();
      if (!active.current) return;
      setVersion(result.data.version);
      if (clearMessage) setMessage("");
    } catch (issue) {
      if (active.current) setError(issue);
    } finally {
      scope.busy.current = false;
      if (active.current) {
        add.reset();
        close.reset();
        withdraw.reset();
        decision.reset();
        revoke.reset();
        setWorking(false);
        scope.refresh();
      }
    }
  }
  const item = detail.data;
  const owner = item?.user_id === user?.id;
  const canSupplement = item && !["closed", "resolved"].includes(item.status);
  return (
    <div className="mx-auto grid w-full max-w-[1440px] gap-5 p-5 lg:p-10">
      <Link href="/ai-quality" className="flex items-center gap-2 text-xs text-sky-800">
        <ArrowLeft className="size-4" />
        我的反馈
      </Link>
      {Boolean(error) && <ErrorNotice error={error} />}
      {detail.error && <ErrorNotice error={detail.error} />}
      {user?.role !== "user" ? (
        <p role="alert">请使用本人学习账号查看反馈。</p>
      ) : item && !owner ? (
        <p role="alert">这条反馈不可访问。</p>
      ) : item ? (
        <>
          <header className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="text-2xl font-bold">{categories[item.category]}</h1>
                <StatusBadge status={item.status} />
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                工单 {item.case_number} · 提交于 {dateLabel(item.created_at)}
              </p>
            </div>
            <div className="flex gap-2">
              {item.status === "submitted" && !item.assignee_id && (
                <Button
                  variant="outline"
                  disabled={working}
                  onClick={() =>
                    void act(() =>
                      withdraw.mutateAsync({ id, body: { expected_version: item.version } }),
                    )
                  }
                >
                  撤回反馈
                </Button>
              )}
              {item.status !== "closed" && (
                <Button
                  variant="outline"
                  disabled={working}
                  onClick={() =>
                    void act(() =>
                      close.mutateAsync({ id, body: { expected_version: item.version } }),
                    )
                  }
                >
                  {item.status === "resolved" ? "确认解决并关闭" : "关闭工单"}
                </Button>
              )}
            </div>
          </header>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
            <div className="grid content-start gap-4">
              <Panel title="我的问题描述">
                <p className="whitespace-pre-wrap text-sm leading-6">
                  {item.description ?? "正文授权已结束，本页不再显示问题描述。"}
                </p>
                {item.expected_result && (
                  <p className="mt-3 rounded-md bg-muted p-3 text-xs text-muted-foreground">
                    期望：{item.expected_result}
                  </p>
                )}
              </Panel>
              <Panel title="关联的 AI 回答">
                <div className="grid gap-4 text-xs sm:grid-cols-3">
                  <div>
                    <p className="mb-2 text-muted-foreground">业务场景</p>学习室 · 资料问答
                  </div>
                  <div className="break-all">
                    <p className="mb-2 text-muted-foreground">Trace</p>
                    {item.trace_id}
                  </div>
                  <div className="break-all">
                    <p className="mb-2 text-muted-foreground">策略版本</p>
                    {item.strategy_version}
                  </div>
                </div>
                <p className="mt-4 rounded-md bg-sky-50 p-3 text-xs text-sky-900">
                  这条反馈仅绑定本次回答，不包括同会话其他内容。
                </p>
              </Panel>
              {item.resolution_summary && (
                <Panel title="处理结论" className="bg-sky-50">
                  <p className="whitespace-pre-wrap text-sm">{item.resolution_summary}</p>
                </Panel>
              )}
              <Panel title="处理进度">
                <EventTimeline events={item.events} />
              </Panel>
            </div>
            <aside className="grid content-start gap-4">
              {item.grants.map((grant) => (
                <GrantCard
                  key={grant.id}
                  grant={grant}
                  working={working}
                  decide={(approved) =>
                    act(() =>
                      decision.mutateAsync({
                        id,
                        grantId: grant.id,
                        body: {
                          expected_version: item.version,
                          expected_grant_version: grant.version,
                          approved,
                        },
                      }),
                    )
                  }
                  revoke={() =>
                    act(() =>
                      revoke.mutateAsync({
                        id,
                        grantId: grant.id,
                        body: {
                          expected_version: item.version,
                          expected_grant_version: grant.version,
                        },
                      }),
                    )
                  }
                />
              ))}
              <Panel title="补充说明">
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (canSupplement && message.trim())
                      void act(
                        () =>
                          add.mutateAsync({
                            id,
                            body: { expected_version: item.version, content: message.trim() },
                          }),
                        true,
                      );
                  }}
                >
                  <Textarea
                    aria-label="补充说明"
                    value={message}
                    onChange={(event) => setMessage(event.target.value)}
                    maxLength={4000}
                    disabled={!canSupplement || working}
                    placeholder="补充复现步骤或期望结果…"
                    className="min-h-[100px]"
                  />
                  <Button
                    type="submit"
                    variant="brand"
                    size="sm"
                    className="mt-3"
                    disabled={!canSupplement || !message.trim() || working}
                  >
                    提交补充
                  </Button>
                  {!canSupplement && (
                    <p className="mt-2 text-xs text-muted-foreground">
                      已解决或关闭的工单不再接受补充。
                    </p>
                  )}
                </form>
              </Panel>
              <p className="flex gap-2 text-xs leading-5 text-muted-foreground">
                <ShieldCheck className="size-4 shrink-0" />
                这里只有对你公开的处理记录，诊断授权仅限本次回答，可随时撤销。
              </p>
            </aside>
          </div>
        </>
      ) : (
        <p role="status" className="text-sm text-muted-foreground">
          {working ? "正在更新反馈…" : "正在加载反馈…"}
        </p>
      )}
    </div>
  );
}
function GrantCard({
  grant,
  working,
  decide,
  revoke,
}: {
  grant: GrantView;
  working: boolean;
  decide: (approved: boolean) => Promise<void>;
  revoke: () => Promise<void>;
}) {
  const valid = new Date(grant.expires_at).getTime() > Date.now();
  const status = !valid && ["active", "pending"].includes(grant.status) ? "expired" : grant.status;
  return (
    <Panel
      title={grant.fields.includes("candidate_excerpts") ? "追加候选片段授权" : "本次诊断授权"}
      className="border-amber-200 bg-amber-50"
    >
      <div className="mb-3 flex items-center justify-between text-xs">
        <span>{grantStatuses[status]}</span>
        <time>到期：{dateLabel(grant.expires_at)}</time>
      </div>
      <p className="mb-3 whitespace-pre-wrap text-sm">{grant.reason}</p>
      {grant.requester_id && (
        <p className="mb-3 break-all text-xs text-muted-foreground">
          申请管理员：{grant.requester_id}
        </p>
      )}
      <p className="text-xs text-muted-foreground">管理员可查看</p>
      <ul className="mt-2 list-inside list-disc space-y-1 text-xs">
        {grant.fields.map((field) => (
          <li key={field}>{grantFields[field]}</li>
        ))}
      </ul>
      {grant.chunk_ids.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium">仅限以下片段</p>
          <ul className="mt-2 space-y-1 break-all text-xs text-muted-foreground">
            {grant.chunk_ids.map((chunk) => (
              <li key={chunk}>{chunk}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="mt-3 text-xs leading-5 text-muted-foreground">
        用于此工单诊断，不包括整份文件、原文件下载或其他会话。
      </p>
      {status === "pending" && (
        <div className="mt-4 flex gap-2">
          <Button variant="brand" size="sm" disabled={working} onClick={() => void decide(true)}>
            同意本次追加授权
          </Button>
          <Button variant="outline" size="sm" disabled={working} onClick={() => void decide(false)}>
            拒绝
          </Button>
        </div>
      )}
      {status === "active" && (
        <Button
          variant="outline"
          size="sm"
          className="mt-4 text-destructive"
          disabled={working}
          onClick={() => void revoke()}
        >
          撤销正文查看授权
        </Button>
      )}
    </Panel>
  );
}
