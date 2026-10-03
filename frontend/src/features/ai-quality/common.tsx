import type { ReactNode } from "react";
import type { CaseView, GrantView, EventView } from "./api";
import { toApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";
export const categories: Record<CaseView["category"], string> = {
  not_found: "未找到相关内容",
  irrelevant_source: "来源不相关",
  wrong_answer: "回答错误",
  wrong_citation: "引用错误",
  outdated_content: "内容过时",
  slow: "响应过慢",
  other: "其他",
};
export const statuses: Record<CaseView["status"], string> = {
  submitted: "待处理",
  triaging: "处理中",
  waiting_user: "待用户补充",
  investigating: "链路诊断中",
  resolved: "已解决",
  closed: "已关闭",
};
export const grantStatuses: Record<GrantView["status"], string> = {
  pending: "待确认",
  active: "有效",
  expired: "已过期",
  revoked: "已撤销",
  rejected: "已拒绝",
};
export const grantFields: Record<GrantView["fields"][number], string> = {
  query: "本次问题",
  final_output: "AI 回答",
  final_citations: "最终引用",
  candidate_excerpts: "指定候选片段",
};
const eventNames: Record<string, string> = {
  case_created: "反馈已提交",
  case_assigned: "管理员已领取",
  case_unassigned: "已取消分配",
  case_transitioned: "处理状态已更新",
  user_message: "用户补充说明",
  admin_message: "管理员回复",
  grant_requested: "请求追加授权",
  grant_approved: "追加授权已同意",
  grant_rejected: "追加授权已拒绝",
  grant_revoked: "正文授权已撤销",
  case_withdrawn: "反馈已撤回",
  case_closed: "工单已关闭",
  diagnostic_replay: "诊断回放已完成",
};
export function dateLabel(value: string | null) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
}
export function StatusBadge({ status }: { status: CaseView["status"] }) {
  return (
    <span
      className={cn(
        "inline-flex rounded-full px-3 py-1 text-xs",
        ["resolved", "closed"].includes(status)
          ? "bg-emerald-50 text-emerald-800"
          : status === "waiting_user" || status === "submitted"
            ? "bg-amber-50 text-amber-800"
            : "bg-sky-50 text-sky-800",
      )}
    >
      {statuses[status]}
    </span>
  );
}
export function Panel({
  title,
  children,
  className,
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-[10px] border border-border bg-surface p-5", className)}>
      {title && <h2 className="mb-4 text-sm font-semibold">{title}</h2>}
      {children}
    </section>
  );
}
export function ErrorNotice({ error }: { error: unknown }) {
  const issue = toApiError(error);
  return (
    <p
      role="alert"
      className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
    >
      {issue.status === 404
        ? "这条反馈不可访问或已失效。"
        : issue.status === 403
          ? "当前账号没有访问权限。"
          : issue.message}
    </p>
  );
}
export function EventTimeline({ events }: { events: EventView[] }) {
  return (
    <ol className="space-y-5">
      {events.length ? (
        events
          .filter((event) => event.visibility === "user")
          .map((event) => (
            <li key={event.id} className="border-l-2 border-border pl-4">
              <div className="flex flex-wrap justify-between gap-2 text-sm">
                <span>{eventNames[event.action] ?? "处理记录已更新"}</span>
                <time className="text-xs text-muted-foreground">{dateLabel(event.created_at)}</time>
              </div>
              {event.content && (
                <p className="mt-2 whitespace-pre-wrap text-sm text-muted-foreground">
                  {event.content}
                </p>
              )}
            </li>
          ))
      ) : (
        <li className="text-sm text-muted-foreground">暂无处理记录</li>
      )}
    </ol>
  );
}
