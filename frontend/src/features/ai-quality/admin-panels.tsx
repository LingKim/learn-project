"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { CheckboxField } from "@/components/ui/checkbox-field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { AdminCaseDetail, GrantView, ReplayRequest, TransitionRequest } from "./api";
import {
  addAdminMessageMutationOptions,
  assignCaseMutationOptions,
  replayCaseMutationOptions,
  requestAccessMutationOptions,
  snapshotQueryOptions,
  transitionCaseMutationOptions,
} from "./queries";

export const statusLabels: Record<AdminCaseDetail["status"], string> = {
  submitted: "待领取",
  triaging: "处理中",
  waiting_user: "待用户补充",
  investigating: "调查中",
  resolved: "已解决",
  closed: "已关闭",
};
export const categoryLabels: Record<AdminCaseDetail["category"], string> = {
  not_found: "未找到内容",
  irrelevant_source: "来源不相关",
  wrong_answer: "回答错误",
  wrong_citation: "引用错误",
  outdated_content: "内容过时",
  slow: "响应过慢",
  other: "其他",
};
export const fieldLabels: Record<GrantView["fields"][number], string> = {
  query: "本次 Query",
  final_output: "最终回答",
  final_citations: "最终引用",
  candidate_excerpts: "指定候选片段正文",
};
const stageLabels: Record<string, string> = {
  query_embedding: "Query 向量化",
  keyword: "FTS",
  vector: "Vector",
  fusion: "融合去重",
  rerank: "Rerank",
  evidence_gate: "证据门禁",
};
const modeLabels: Record<ReplayRequest["mode"], string> = {
  fts_only: "FTS-only",
  vector_only: "Vector-only",
  hybrid_only: "Hybrid-only",
  without_rerank: "无 Rerank",
  full: "完整策略",
};
const grantLabels: Record<GrantView["status"], string> = {
  pending: "待用户确认",
  active: "有效",
  expired: "已到期",
  revoked: "已撤销",
  rejected: "已拒绝",
};

export function Panel({
  title,
  children,
  className = "",
}: {
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-lg border border-border bg-surface p-5 ${className}`}>
      <h2 className="mb-4 text-sm font-medium">{title}</h2>
      {children}
    </section>
  );
}
export function Choice({
  label,
  value,
  choices,
  onChange,
  disabled,
}: {
  label: string;
  value: string;
  choices: Record<string, string>;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <Select value={value} onValueChange={onChange} disabled={disabled}>
        <SelectTrigger aria-label={label}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {Object.entries(choices).map(([key, text]) => (
            <SelectItem key={key} value={key}>
              {text}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
export function QueryProblem({ error, retry }: { error: Error; retry: () => void }) {
  return (
    <div role="alert" className="rounded-md border border-border p-4">
      <p>{error.message}</p>
      <Button variant="outline" size="sm" className="mt-2" onClick={retry}>
        重试
      </Button>
    </div>
  );
}
export function localTime(value: string) {
  return new Date(value).toLocaleString("zh-CN");
}
export function grantActive(grant: GrantView, detail: AdminCaseDetail) {
  return (
    detail.status !== "closed" &&
    grant.status === "active" &&
    Date.parse(grant.expires_at) > Date.now()
  );
}

export function TracePanel({ detail }: { detail: AdminCaseDetail }) {
  const trace = detail.trace;
  if (!trace)
    return (
      <Panel title="链路诊断">
        <p role="status">链路不可用：{detail.source_error ?? "未记录完整 Trace"}</p>
      </Panel>
    );
  const stages = ["query_embedding", "keyword", "vector", "fusion", "rerank", "evidence_gate"];
  const chunkIds = [
    ...new Set(
      trace.stages.flatMap((stage) =>
        (stage.candidates ?? []).map((candidate) => candidate.chunk_id),
      ),
    ),
  ];
  return (
    <div className="space-y-4">
      <Panel title="链路元数据">
        <dl className="grid gap-4 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-muted-foreground">Trace ID</dt>
            <dd className="break-all">{trace.trace_id}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">策略版本</dt>
            <dd className="break-all">{trace.strategy_version}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">记录时间</dt>
            <dd>{localTime(trace.occurred_at)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">错误码</dt>
            <dd>{trace.error_code ?? "无记录错误"}</dd>
          </div>
        </dl>
      </Panel>
      <Panel title="检索阶段瀑布">
        <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
          {stages.map((name) => {
            const stage = trace.stages.find((item) => item.stage === name);
            return (
              <div key={name} className="rounded-md bg-muted p-3 text-xs">
                <h3 className="mb-2 font-medium">{stageLabels[name]}</h3>
                <p>
                  {stage
                    ? `${stage.count ?? stage.candidates?.length ?? "未记录"} 候选`
                    : "阶段缺失"}
                </p>
                <p className="mt-2 text-muted-foreground">
                  {stage?.elapsed_ms != null ? `${stage.elapsed_ms} ms` : "耗时未记录"}
                </p>
              </div>
            );
          })}
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          解析 / 索引、生成 / 引用阶段未提供独立阶段记录；不以零耗时或成功补齐。
        </p>
      </Panel>
      <Panel title="同一片段的记录排名与分数">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Chunk ID</TableHead>
              {["keyword", "vector", "fusion", "rerank"].map((name) => (
                <TableHead key={name}>{stageLabels[name]}</TableHead>
              ))}
              <TableHead>最终结果</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {chunkIds.map((id) => (
              <TableRow key={id}>
                <TableCell className="max-w-52 break-all">{id}</TableCell>
                {["keyword", "vector", "fusion", "rerank"].map((name) => {
                  const found = trace.stages
                    .find((stage) => stage.stage === name)
                    ?.candidates?.find((candidate) => candidate.chunk_id === id);
                  return (
                    <TableCell key={name}>
                      {found ? `#${found.rank} · ${found.score.toFixed(4)}` : "未入选 / 未记录"}
                    </TableCell>
                  );
                })}
                <TableCell>
                  {trace.final_chunk_ids.indexOf(id) >= 0
                    ? `#${trace.final_chunk_ids.indexOf(id) + 1}`
                    : "未入选"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {!chunkIds.length && <p className="py-4 text-sm text-muted-foreground">未记录候选排名</p>}
        <p className="mt-3 text-xs text-muted-foreground">
          当前接口没有逐片段过滤原因；候选来自某一路不构成技术归因。
        </p>
      </Panel>
      <Panel title="提示词与模型版本元数据">
        <pre className="overflow-auto text-xs">
          {JSON.stringify(
            { prompt_manifest: trace.prompt_manifest, model_parameters: trace.model_parameters },
            null,
            2,
          )}
        </pre>
      </Panel>
    </div>
  );
}

function SnapshotFields({ detail, grant }: { detail: AdminCaseDetail; grant: GrantView }) {
  const client = useQueryClient();
  const [fields, setFields] = useState<GrantView["fields"]>([]);
  const [requested, setRequested] = useState<GrantView["fields"]>([]);
  const valid = grantActive(grant, detail);
  // 授权范围和版本均进入查询键；读正文是明确操作，未选择字段不会请求。
  const snapshot = useQuery({
    ...snapshotQueryOptions(client, detail.id, detail.version, {
      grant_id: grant.id,
      expected_grant_version: grant.version,
      fields: requested,
    }),
    enabled: valid && requested.length > 0,
  });
  return (
    <div className="space-y-2 border-t border-border pt-3">
      {grant.fields.map((field) => (
        <CheckboxField
          key={field}
          label={fieldLabels[field]}
          checked={fields.includes(field)}
          disabled={!valid}
          onCheckedChange={(checked) => {
            setFields((current) =>
              checked === true ? [...current, field] : current.filter((value) => value !== field),
            );
            setRequested([]);
          }}
        />
      ))}
      <Button
        variant="outline"
        size="sm"
        disabled={!valid || !fields.length || snapshot.isFetching}
        onClick={() => setRequested([...fields])}
      >
        读取已选择的授权字段
      </Button>
      {snapshot.isFetching && <p role="status">正在读取授权字段…</p>}
      {snapshot.error && (
        <QueryProblem error={snapshot.error} retry={() => void snapshot.refetch()} />
      )}
      {valid && snapshot.data && (
        <div className="space-y-3 text-sm">
          <p className="whitespace-pre-wrap">{snapshot.data.description}</p>
          {snapshot.data.expected_result && (
            <p className="whitespace-pre-wrap">期望结果：{snapshot.data.expected_result}</p>
          )}
          {Object.entries(snapshot.data.values).map(([field, value]) => (
            <div key={field}>
              <h3 className="font-medium">
                {fieldLabels[field as GrantView["fields"][number]] ?? field}
              </h3>
              <pre className="mt-1 max-h-80 overflow-auto whitespace-pre-wrap break-all text-xs">
                {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
export function GrantPanel({ detail, busy }: { detail: AdminCaseDetail; busy: boolean }) {
  return (
    <Panel title="当前可查看范围" className="bg-[#fff7d8]">
      <p className="mb-3 text-xs text-muted-foreground">
        正文只在有效授权范围内显示；整份文件、其他会话和下载不在范围内。
      </p>
      {!detail.grants.length && <p>暂无授权</p>}
      {detail.grants.map((grant) => (
        <div key={grant.id} className="mb-4 space-y-2 text-sm">
          <p className="font-medium">
            {
              grantLabels[
                ["active", "pending"].includes(grant.status) &&
                Date.parse(grant.expires_at) <= Date.now()
                  ? "expired"
                  : grant.status
              ]
            }{" "}
            · 授权 v{grant.version}
          </p>
          <p>{grant.reason}</p>
          <p className="text-xs">{localTime(grant.expires_at)} 到期</p>
          {grant.chunk_ids.length > 0 && (
            <p className="break-all text-xs">指定片段：{grant.chunk_ids.join("、")}</p>
          )}
          {!busy && grantActive(grant, detail) && (
            <SnapshotFields
              key={`${detail.version}:${grant.id}:${grant.version}`}
              detail={detail}
              grant={grant}
            />
          )}
        </div>
      ))}
    </Panel>
  );
}

export function ReplayPanel({ detail }: { detail: AdminCaseDetail }) {
  return (
    <Panel title="记录候选离线对照">
      <p className="mb-4 text-sm text-muted-foreground">
        仅比较历史候选排序，不重新检索或调用模型；不测量独立负载耗时，不证明因果关系。当前
        Hybrid-only 与无 Rerank 使用同一融合记录。
      </p>
      {!detail.replays.length && <p>暂无回放记录</p>}
      {detail.replays.map((replay) => (
        <div key={replay.id} className="mb-5 border-t border-border pt-3">
          <h3 className="text-sm font-medium">
            {modeLabels[replay.mode]} · {replay.status === "succeeded" ? "完成" : "失败"}
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">
            {localTime(replay.created_at)} · {replay.strategy_version}
          </p>
          <p className="mt-2 text-sm">{replay.note}</p>
          {replay.error_key && <p role="alert">{replay.error_key}</p>}
          <dl className="my-3 flex flex-wrap gap-5 text-xs">
            {Object.entries(replay.metrics).map(([name, value]) => (
              <div key={name}>
                <dt>{name}</dt>
                <dd>{value == null ? "未提供目标 / 不可计算" : value.toFixed(4)}</dd>
              </div>
            ))}
          </dl>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Chunk ID</TableHead>
                <TableHead>排名</TableHead>
                <TableHead>分数</TableHead>
                <TableHead>该模式结果</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {replay.ranking.map((entry) => (
                <TableRow key={entry.chunk_id}>
                  <TableCell className="break-all">{entry.chunk_id}</TableCell>
                  <TableCell>{entry.rank}</TableCell>
                  <TableCell>{entry.score.toFixed(4)}</TableCell>
                  <TableCell>
                    {replay.final_chunk_ids.includes(entry.chunk_id) ? "入选" : "未入选"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ))}
    </Panel>
  );
}

const actionLabels: Record<string, string> = {
  case_created: "反馈已提交",
  case_assigned: "管理员已领取 / 转交",
  user_message: "用户补充说明",
  admin_message: "管理员公开回复",
  admin_reply: "管理员公开回复",
  internal_note: "管理员内部备注",
  message_public: "提交公开回复",
  message_internal: "提交内部备注",
  admin_note: "管理员内部备注",
  grant_requested: "请求追加授权",
  grant_approved: "追加授权已同意",
  grant_rejected: "追加授权已拒绝",
  grant_revoked: "正文授权已撤销",
  case_withdrawn: "反馈已撤回",
  case_closed: "工单已关闭",
  case_triaging: "工单进入处理",
  case_waiting_user: "等待用户补充",
  case_investigating: "工单进入调查",
  case_resolved: "工单已解决",
  replay_completed: "离线对照已完成",
  replay_failed: "离线对照失败",
  case_create: "提交反馈",
  case_user_detail: "用户读取工单",
  case_queue: "查询后台工单队列",
  case_user_list: "查询个人工单",
  case_user_message: "用户补充说明",
  case_withdraw: "撤回工单",
  case_user_close: "用户关闭工单",
  grant_decision: "追加授权决定",
  grant_revoke: "撤销正文授权",
  case_admin_detail: "管理员读取工单",
  case_assign: "领取 / 转交工单",
  grant_request: "请求追加授权",
  snapshot_read: "读取授权快照",
  case_admin_message: "管理员回复 / 备注",
  case_transition: "修改工单状态",
  replay_create: "运行离线对照",
  quality_overview: "读取质量概览",
};

export function HistoryPanel({ detail }: { detail: AdminCaseDetail }) {
  return (
    <div className="space-y-4">
      <Panel title="处理记录">
        <ol className="space-y-4">
          {detail.events.map((event) => (
            <li key={event.id} className="border-l-2 border-border pl-4 text-sm">
              <p>
                {actionLabels[event.action] ?? "处理记录已更新"} ·{" "}
                {event.visibility === "admin" ? "内部（仅管理员）" : "公开（用户可见）"} · v
                {event.version}
              </p>
              <p className="text-xs text-muted-foreground">{localTime(event.created_at)}</p>
              {event.content && <p className="mt-1 whitespace-pre-wrap">{event.content}</p>}
            </li>
          ))}
        </ol>
        {!detail.events.length && <p>暂无处理记录</p>}
      </Panel>
      <Panel title="敏感访问审计">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>时间</TableHead>
              <TableHead>动作</TableHead>
              <TableHead>执行人</TableHead>
              <TableHead>字段</TableHead>
              <TableHead>结果 / 原因码</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {detail.audits.map((audit, index) => (
              <TableRow key={`${audit.occurred_at}:${index}`}>
                <TableCell>{localTime(audit.occurred_at)}</TableCell>
                <TableCell>{actionLabels[audit.action] ?? "工单操作"}</TableCell>
                <TableCell>{audit.actor_id ?? "—"}</TableCell>
                <TableCell>
                  {audit.fields.map((field) => fieldLabels[field]).join("、") || "—"}
                </TableCell>
                <TableCell>
                  {audit.outcome === "allowed" || audit.outcome === "success"
                    ? "成功"
                    : audit.outcome === "denied" || audit.outcome === "failure"
                      ? "拒绝 / 失败"
                      : audit.outcome}{" "}
                  / {audit.reason_code ?? "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {!detail.audits.length && <p className="py-3 text-sm">暂无审计记录</p>}
      </Panel>
    </div>
  );
}

const transitions: Record<AdminCaseDetail["status"], AdminCaseDetail["status"][]> = {
  submitted: ["triaging", "closed"],
  triaging: ["waiting_user", "investigating", "resolved", "closed"],
  waiting_user: ["triaging", "investigating", "resolved", "closed"],
  investigating: ["waiting_user", "resolved", "closed"],
  resolved: ["closed"],
  closed: [],
};
export const resolutionLabels: Record<NonNullable<TransitionRequest["resolution_code"]>, string> = {
  parsing_gap: "解析缺口",
  stale_index: "索引过时",
  fts_filter: "FTS 过滤",
  vector_recall: "向量召回",
  fusion: "融合",
  rerank: "重排序",
  evidence_gate: "证据门禁",
  generation: "生成",
  citation: "引用",
  source_outdated: "来源过时",
  latency: "耗时",
  not_reproduced: "未复现",
  user_expectation: "用户期望",
  unknown: "未知",
};
function chunkIds(value: string) {
  return [...new Set(value.split(/[\s,，]+/).filter(Boolean))];
}

export function AdminActions({
  detail,
  actorId,
  onStart,
  onFinished,
  refreshing = false,
}: {
  detail: AdminCaseDetail;
  actorId: string;
  onStart: () => void;
  onFinished: () => Promise<void>;
  refreshing?: boolean;
}) {
  const client = useQueryClient();
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const assign = useMutation(assignCaseMutationOptions(client, () => mounted.current));
  const access = useMutation(requestAccessMutationOptions(client, () => mounted.current));
  const replay = useMutation(replayCaseMutationOptions(client, () => mounted.current));
  const message = useMutation(addAdminMessageMutationOptions(client, () => mounted.current));
  const transition = useMutation(transitionCaseMutationOptions(client, () => mounted.current));
  const [action, setAction] = useState("assign");
  const [assignee, setAssignee] = useState(actorId);
  const [reason, setReason] = useState("");
  const [chunks, setChunks] = useState("");
  const [days, setDays] = useState("30");
  const [mode, setMode] = useState<ReplayRequest["mode"]>("full");
  const [grantId, setGrantId] = useState("");
  const [content, setContent] = useState("");
  const [visibility, setVisibility] = useState<"user" | "admin">("user");
  const [target, setTarget] = useState<AdminCaseDetail["status"]>(
    transitions[detail.status][0] ?? "closed",
  );
  const [code, setCode] = useState<NonNullable<TransitionRequest["resolution_code"]>>("unknown");
  const [summary, setSummary] = useState("");
  const [replayId, setReplayId] = useState("none");
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const activeGrants = detail.grants.filter((grant) => grantActive(grant, detail));
  const selectedGrant = activeGrants.find((grant) => grant.id === grantId);
  const closed = detail.status === "closed";
  // 候选正文授权只能在处理中申请，和后端已有状态约束保持一致。
  const canRequestAccess = ["triaging", "investigating", "waiting_user"].includes(detail.status);
  async function submit() {
    if (!mounted.current || invalid) return;
    setError(null);
    setWorking(true);
    onStart();
    try {
      const expected_version = detail.version;
      if (action === "assign")
        await assign.mutateAsync({
          id: detail.id,
          body: { expected_version, assignee_id: assignee },
        });
      else if (action === "access")
        await access.mutateAsync({
          id: detail.id,
          body: {
            expected_version,
            reason,
            chunk_ids: chunkIds(chunks),
            duration_days: Number(days),
          },
        });
      else if (action === "replay" && selectedGrant)
        await replay.mutateAsync({
          id: detail.id,
          body: {
            expected_version,
            grant_id: selectedGrant.id,
            expected_grant_version: selectedGrant.version,
            mode,
            target_chunk_ids: chunkIds(chunks),
          },
        });
      else if (action === "message") {
        await message.mutateAsync({
          id: detail.id,
          body: { expected_version, content, visibility },
        });
        if (mounted.current) setContent("");
      } else if (action === "transition")
        await transition.mutateAsync({
          id: detail.id,
          body: {
            expected_version,
            status: target,
            ...(target === "resolved"
              ? {
                  resolution_code: code,
                  resolution_summary: summary,
                  ...(replayId !== "none" ? { replay_id: replayId } : {}),
                }
              : {}),
          },
        });
    } catch (cause) {
      if (mounted.current) setError(cause instanceof Error ? cause.message : "操作失败");
    } finally {
      assign.reset();
      access.reset();
      replay.reset();
      message.reset();
      transition.reset();
      if (mounted.current) {
        await onFinished();
        if (mounted.current) setWorking(false);
      }
    }
  }
  const invalid =
    closed ||
    working ||
    refreshing ||
    (action === "assign" && !assignee.trim()) ||
    (action === "access" &&
      (!canRequestAccess ||
        !reason.trim() ||
        !chunkIds(chunks).length ||
        Number(days) < 1 ||
        Number(days) > 30 ||
        !Number.isInteger(Number(days)))) ||
    (action === "replay" && !selectedGrant) ||
    (action === "message" && !content.trim()) ||
    (action === "transition" &&
      (!transitions[detail.status].includes(target) || (target === "resolved" && !summary.trim())));
  return (
    <Panel title="工单处置">
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <fieldset className="space-y-4" disabled={working || refreshing || closed}>
          <Choice
            label="操作"
            value={action}
            onChange={setAction}
            disabled={working || refreshing || closed}
            choices={{
              assign: "领取 / 转交",
              access: "请求候选片段追加授权",
              replay: "运行记录候选离线对照",
              message: "回复 / 内部备注",
              transition: "状态与解决归因",
            }}
          />
          {action === "assign" && (
            <div className="space-y-2">
              <Label htmlFor="quality-assignee">负责人 UUID</Label>
              <Input
                id="quality-assignee"
                value={assignee}
                onChange={(event) => setAssignee(event.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                默认填写当前管理员，转交须填写实际管理员 ID。
              </p>
            </div>
          )}
          {action === "access" && (
            <>
              {!canRequestAccess && (
                <p className="text-sm text-muted-foreground">
                  {detail.status === "submitted"
                    ? "先领取工单，再申请候选片段授权"
                    : "当前工单状态不支持申请候选片段授权。"}
                </p>
              )}
              <div className="space-y-2">
                <Label htmlFor="quality-purpose">诊断用途</Label>
                <Textarea
                  id="quality-purpose"
                  required
                  maxLength={1000}
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="quality-days">有效天数（1–30）</Label>
                <Input
                  id="quality-days"
                  type="number"
                  min={1}
                  max={30}
                  value={days}
                  onChange={(event) => setDays(event.target.value)}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                请求仅涉及下面指定的候选片段，需用户单独确认。
              </p>
            </>
          )}
          {action === "replay" && (
            <>
              <Choice
                label="使用授权"
                value={grantId || "none"}
                onChange={setGrantId}
                choices={{
                  none: "请选择有效授权",
                  ...Object.fromEntries(
                    activeGrants.map((grant) => [
                      grant.id,
                      `v${grant.version} · ${grant.fields.map((field) => fieldLabels[field]).join("、")}`,
                    ]),
                  ),
                }}
              />
              <Choice
                label="对照模式"
                value={mode}
                onChange={(value) => setMode(value as ReplayRequest["mode"])}
                choices={modeLabels}
              />
              <p className="text-xs text-muted-foreground">
                历史记录排序比较，不独立测量耗时或证明因果。
              </p>
            </>
          )}
          {(action === "access" || action === "replay") && (
            <div className="space-y-2">
              <Label htmlFor="quality-chunks">
                {action === "access"
                  ? "指定候选 Chunk IDs（必填）"
                  : "目标 Chunk IDs（可选，用于指标）"}
              </Label>
              <Textarea
                id="quality-chunks"
                value={chunks}
                onChange={(event) => setChunks(event.target.value)}
                placeholder="以逗号或换行分隔 UUID"
              />
            </div>
          )}
          {action === "message" && (
            <>
              <Choice
                label="可见范围"
                value={visibility}
                onChange={(value) => setVisibility(value as "user" | "admin")}
                choices={{ user: "公开回复（用户可见）", admin: "内部备注（仅管理员）" }}
              />
              <div className="space-y-2">
                <Label htmlFor="quality-message">
                  {visibility === "admin" ? "内部备注" : "公开回复"}
                </Label>
                <Textarea
                  id="quality-message"
                  maxLength={4000}
                  required
                  value={content}
                  onChange={(event) => setContent(event.target.value)}
                  placeholder="记录判断和结论，请勿复制用户正文或凭据"
                />
              </div>
            </>
          )}
          {action === "transition" && (
            <>
              <Choice
                label="目标状态"
                value={target}
                onChange={(value) => setTarget(value as AdminCaseDetail["status"])}
                choices={Object.fromEntries(
                  transitions[detail.status].map((value) => [value, statusLabels[value]]),
                )}
              />
              {target === "resolved" && (
                <>
                  <Choice
                    label="解决归因"
                    value={code}
                    onChange={(value) =>
                      setCode(value as NonNullable<TransitionRequest["resolution_code"]>)
                    }
                    choices={resolutionLabels}
                  />
                  <div className="space-y-2">
                    <Label htmlFor="quality-summary">公开结论（必填）</Label>
                    <Textarea
                      id="quality-summary"
                      required
                      maxLength={2000}
                      value={summary}
                      onChange={(event) => setSummary(event.target.value)}
                    />
                  </div>
                  <Choice
                    label="对应对照记录"
                    value={replayId}
                    onChange={setReplayId}
                    choices={{
                      none: "无对照记录",
                      ...Object.fromEntries(
                        detail.replays
                          .filter((item) => item.status === "succeeded")
                          .map((item) => [
                            item.id,
                            `${modeLabels[item.mode]} · ${localTime(item.created_at)}`,
                          ]),
                      ),
                    }}
                  />
                  <p className="text-xs text-muted-foreground">
                    技术归因需后端验证对照差异；来源标签或不可回放错误本身不能证明技术原因。
                  </p>
                </>
              )}
            </>
          )}
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          {closed && (
            <p className="text-sm text-muted-foreground">工单已关闭，正文授权和处置操作不可用。</p>
          )}
          <Button type="submit" variant="brand" disabled={invalid}>
            {working ? "提交中…" : "提交操作"}
          </Button>
        </fieldset>
      </form>
    </Panel>
  );
}
