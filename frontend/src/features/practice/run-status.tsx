"use client";

import { useMutation } from "@tanstack/react-query";
import { LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { RunView } from "./api";
import { cancelRunOptions, retryRunOptions, isActiveRun } from "./queries";
import { useActiveContext } from "./use-active-context";

const stages: Record<string, string> = {
  pending: "等待处理",
  resolving_context: "解析学习上下文",
  retrieving: "检索资料",
  generating: "生成题目",
  validating: "校验结果",
  publishing: "保存结果",
  context: "解析学习上下文",
  retrieval: "检索资料",
  retrieve: "检索资料",
  generation: "生成题目",
  generate: "生成题目",
  model: "生成内容",
  validate: "校验结果",
  publish: "保存结果",
  planning: "生成配置建议",
  grading: "评价答案",
  cancelled: "已取消",
  succeeded: "已完成",
  failed: "未完成",
};
export function practiceError(key: string | null | undefined) {
  if (key === "PRACTICE_EVIDENCE_INSUFFICIENT")
    return "资料不足：选定资料未能支持题目与答案，请调整知识点或补充有效资料。";
  if (key === "PRACTICE_SOURCE_CHANGED")
    return "来源已失效：原资料已删除、移动或重新解析；历史结果仍可读。请创建新练习。";
  if (key === "PRACTICE_VERSION_CONFLICT" || key === "PRACTICE_PLAN_STALE")
    return "其他页面已更新版本，请读取最新配置后重新确认。";
  if (key === "PRACTICE_RUN_TIMEOUT") return "任务超时，已有题目、答案和点评保持不变。";
  if (key === "PRACTICE_GRADE_INVALID") return "点评未通过证据校验，已提交答案保留，可明确重试。";
  if (key === "PRACTICE_GENERATION_INVALID")
    return "本次结果未通过题目校验，原题集不变，可明确重试。";
  if (key === "PRACTICE_PROVIDER_UNAVAILABLE") return "模型服务暂不可用，可稍后明确重试。";
  return "任务未完成，已有内容保持不变，请检查配置或重试。";
}
export function RunStatus({
  run,
  onChange,
  onAdjust,
}: {
  run: RunView;
  onChange: (run: RunView) => void;
  onAdjust: () => void;
}) {
  const isCurrent = useActiveContext(run.id);
  const cancel = useMutation(cancelRunOptions());
  const retry = useMutation(retryRunOptions());
  async function action(kind: "cancel" | "retry") {
    const result =
      kind === "cancel"
        ? await cancel.mutateAsync(run.id)
        : await retry.mutateAsync({
            id: run.id,
            body: { request_key: run.request_key, input_digest: run.input_digest },
          });
    // 缓存由父页面的上下文保护统一更新；取消响应不能在离开后重新填入旧数据。
    if (isCurrent()) onChange(result.data);
  }
  const pending = isActiveRun(run);
  if (run.status === "succeeded")
    return (
      <p role="status" className="text-xs text-success">
        任务已完成 · 正在读取已保存的结果
      </p>
    );
  return (
    <div className="my-4 space-y-2 rounded-lg border border-border bg-muted p-4" aria-live="polite">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="flex items-center gap-2 text-sm font-semibold">
          {pending ? (
            <LoaderCircle
              aria-hidden="true"
              className="size-4 animate-spin motion-reduce:animate-none"
            />
          ) : null}
          {pending
            ? run.status === "cancel_requested"
              ? "正在取消任务"
              : (stages[run.stage] ?? "正在处理练习任务")
            : run.status === "cancelled"
              ? "任务已取消，已有内容保持不变。"
              : practiceError(run.error_key)}
        </p>
        {pending ? (
          <Button
            size="sm"
            variant="outline"
            disabled={cancel.isPending || run.status === "cancel_requested"}
            onClick={() => {
              void action("cancel").catch(() => {});
            }}
          >
            取消任务
          </Button>
        ) : run.status === "failed" && run.retryable ? (
          <Button
            size="sm"
            variant="outline"
            disabled={retry.isPending}
            onClick={() => {
              void action("retry").catch(() => {});
            }}
          >
            重试任务
          </Button>
        ) : (
          <Button size="sm" variant="outline" onClick={onAdjust}>
            返回修改
          </Button>
        )}
      </div>
      {pending ? (
        <p className="text-xs text-muted-foreground">
          刷新仍可查看实际处理状态，断开页面不会取消任务。
        </p>
      ) : null}
      {cancel.error || retry.error ? (
        <p role="alert" className="text-sm text-danger">
          {cancel.error?.message ?? retry.error?.message}
        </p>
      ) : null}
    </div>
  );
}
