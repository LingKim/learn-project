import { Badge } from "@/components/ui/badge";
import { toApiError } from "@/lib/api/errors";
import type { VersionSummary } from "./api";

export function dateText(value: string | null | undefined) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("zh-CN");
}
export function VersionBadge({ status }: { status: VersionSummary["status"] }) {
  return (
    <Badge variant={status === "published" ? "success" : status === "draft" ? "warm" : "outline"}>
      {{ draft: "草稿", published: "已发布", retired: "已退役" }[status]}
    </Badge>
  );
}
export function PromptError({ error }: { error: unknown }) {
  const value = toApiError(error);
  return (
    <div
      role="alert"
      className="rounded-md border border-danger/30 bg-surface px-4 py-3 text-sm text-danger"
    >
      <p>{value.message}</p>
      {value.status === 409 && (
        <p className="mt-1">版本已变化。当前输入已保留，请核对最新版本后再操作。</p>
      )}
      {value.requestId && <p className="mt-1 text-xs">请求编号：{value.requestId}</p>}
    </div>
  );
}
export function JsonView({ value }: { value: unknown }) {
  return (
    <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-md border border-border bg-sidebar/40 p-3 text-xs leading-6">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}
