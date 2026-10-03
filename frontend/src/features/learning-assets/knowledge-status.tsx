"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { KnowledgeRunView } from "./api";
import {
  cancelKnowledgeOptions,
  retryKnowledgeOptions,
  learningAssetKeys,
  activeKnowledgeRun,
} from "./queries";

const stages: Record<string, string> = {
  pending: "等待处理",
  resolving_context: "解析学习上下文",
  context: "解析学习上下文",
  retrieving: "检索资料",
  retrieval: "检索资料",
  generating: "生成精讲内容",
  generation: "生成精讲内容",
  validating: "校验内容与引用",
  publishing: "保存卡片",
  cancelled: "已取消",
  failed: "生成未完成",
  succeeded: "已完成",
};
export function knowledgeError(key?: string | null) {
  if (key === "LEARNING_ASSET_SOURCE_CHANGED")
    return "来源已改变，请核对资料范围后显式重新生成；已有卡片保留。";
  if (key === "KNOWLEDGE_EVIDENCE_INSUFFICIENT")
    return "资料不足，无法支持完整精讲，请调整知识点或补充有效资料。";
  if (key === "KNOWLEDGE_OUTPUT_INVALID") return "生成内容未通过结构或引用校验，可明确重试。";
  if (key === "KNOWLEDGE_PROVIDER_UNAVAILABLE") return "模型服务暂不可用，可稍后明确重试。";
  if (key === "KNOWLEDGE_RUN_TIMEOUT") return "任务超时，已有卡片保留，可明确重试。";
  return "本次生成未完成，已有卡片保留。";
}
export function KnowledgeStatus({
  run,
  onAdjust,
}: {
  run: KnowledgeRunView;
  onAdjust?: () => void;
}) {
  const client = useQueryClient();
  const cancel = useMutation(cancelKnowledgeOptions());
  const retry = useMutation(retryKnowledgeOptions());
  const active = activeKnowledgeRun(run);
  async function action(kind: "cancel" | "retry") {
    const result =
      kind === "cancel"
        ? await cancel.mutateAsync(run.id)
        : await retry.mutateAsync({
            id: run.id,
            body: { request_key: run.request_key, input_digest: run.input_digest },
          });
    client.setQueryData(learningAssetKeys.run(run.id), result.data);
    await client.invalidateQueries({ queryKey: learningAssetKeys.all });
  }
  if (run.status === "succeeded")
    return (
      <p role="status" className="my-3 text-xs text-success">
        任务已完成 · 卡片版本 {run.result_ref?.version ?? "已保存"}
      </p>
    );
  return (
    <section
      aria-label="精讲任务"
      aria-live="polite"
      className="my-4 space-y-3 rounded-lg border border-border bg-sidebar p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="flex items-center gap-2 text-sm font-semibold">
          {active ? (
            <LoaderCircle
              aria-hidden="true"
              className="size-4 animate-spin motion-reduce:animate-none"
            />
          ) : null}
          {active
            ? run.status === "cancel_requested"
              ? "正在取消任务"
              : (stages[run.stage] ?? "正在处理精讲任务")
            : run.status === "cancelled"
              ? "任务已取消，已有卡片保留。"
              : knowledgeError(run.error_key)}
        </p>
        {active ? (
          <Button
            type="button"
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
            type="button"
            size="sm"
            variant="outline"
            disabled={retry.isPending}
            onClick={() => {
              void action("retry").catch(() => {});
            }}
          >
            重试任务
          </Button>
        ) : onAdjust ? (
          <Button type="button" size="sm" variant="outline" onClick={onAdjust}>
            调整配置
          </Button>
        ) : null}
      </div>
      {active ? (
        <p className="text-xs text-muted-foreground">
          刷新可恢复实际处理状态，关闭页面不会取消任务。
        </p>
      ) : null}
      {cancel.error || retry.error ? (
        <p role="alert" className="text-sm text-danger">
          {cancel.error?.message ?? retry.error?.message}
        </p>
      ) : null}
    </section>
  );
}
