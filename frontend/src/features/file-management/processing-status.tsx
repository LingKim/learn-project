"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { KnowledgeFileView, ProcessingTaskView } from "./api";
import {
  aiConsentQueryOptions,
  confirmAIConsentMutationOptions,
  processingMutationOptions,
  processingTaskQueryOptions,
} from "./queries";

const stages: Record<string, string> = {
  waiting: "等待处理",
  downloading: "下载原件",
  extracting: "提取正文",
  ocr: "识别扫描页",
  chunking: "文本分块",
  embedding: "生成向量",
  indexing: "写入索引",
  publishing: "发布版本",
};
const failures: Record<string, string> = {
  DOCUMENT_OCR_NO_TEXT: "扫描页未识别到有效文字",
  DOCUMENT_OCR_LOW_CONFIDENCE: "识别文字未通过质量检查，请重试解析",
  DOCUMENT_OCR_OUTPUT_INCOMPLETE: "识别输出不完整，请检查页面内容",
  DOCUMENT_OCR_LIMIT_EXCEEDED: "扫描页数量或图片大小超过处理限制",
  DOCUMENT_NO_TEXT: "资料不包含可用正文",
  DOCUMENT_STRUCTURE_INVALID: "文档损坏或结构不受支持",
};

export function processingDescription(task: ProcessingTaskView): string {
  if (task.requires_ai_consent && task.status === "pending") return "等待确认 AI 资料处理说明";
  if (task.status === "cancel_requested") return "正在取消，原件保留";
  if (task.status === "cancelled")
    return task.active_version ? "最近解析已取消，旧版本仍可检索" : "已取消，原件保留";
  if (task.status === "failed")
    return (
      (task.active_version ? "最近解析失败，旧版本仍可检索：" : "") +
      (failures[task.last_error_code ?? ""] ?? "处理失败，请稍后重试或检查服务配置")
    );
  if (task.status === "succeeded")
    return `已索引 ${task.active_version?.chunk_count ?? task.completed_units ?? 0} 个片段`;
  const label = stages[task.stage] ?? "处理中";
  return task.total_units !== null && task.completed_units !== null
    ? `${label} ${task.completed_units} / ${task.total_units}`
    : label;
}

export function AIProcessingNotice() {
  const client = useQueryClient();
  const consent = useQuery(aiConsentQueryOptions());
  const confirm = useMutation(confirmAIConsentMutationOptions(client));
  const [open, setOpen] = useState(false);
  const [checked, setChecked] = useState(false);
  if (consent.isError)
    return (
      <p role="alert" className="mb-4 text-sm text-destructive">
        AI 处理说明暂时无法读取，请稍后重试。
        <Button variant="ghost" onClick={() => void consent.refetch()}>
          重试
        </Button>
      </p>
    );
  if (!consent.data || consent.data.confirmed) return null;
  return (
    <>
      <div className="mb-4 flex items-center justify-between gap-4 rounded-md border bg-muted p-3 text-sm">
        <p>首次解析前请确认 AI 处理说明。上传并校验通过的资料将自动建立检索索引。</p>
        <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
          查看并确认
        </Button>
      </div>
      <Dialog
        open={open}
        onOpenChange={(value) => {
          setOpen(value);
          if (!value) setChecked(false);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>AI 资料处理说明</DialogTitle>
            <DialogDescription>{consent.data.notice}</DialogDescription>
          </DialogHeader>
          <label className="flex items-start gap-3 text-sm">
            <Checkbox checked={checked} onCheckedChange={(value) => setChecked(value === true)} />
            我已阅读并同意上述资料处理方式
          </label>
          {confirm.isError ? (
            <p role="alert" className="text-sm text-destructive">
              确认失败，请重试。
            </p>
          ) : null}
          <DialogFooter>
            <Button
              disabled={!checked || confirm.isPending}
              onClick={() => {
                if (consent.data)
                  confirm.mutate(
                    { confirmed: true, terms_version: consent.data.terms_version },
                    { onSuccess: () => setOpen(false) },
                  );
              }}
            >
              确认并开始处理
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export function DocumentProcessingStatus({
  knowledgeBaseId,
  file,
}: {
  knowledgeBaseId: string;
  file: KnowledgeFileView;
}) {
  const client = useQueryClient();
  const query = useQuery(processingTaskQueryOptions(knowledgeBaseId, file.id));
  const start = useMutation(processingMutationOptions(client, "start"));
  const cancel = useMutation(processingMutationOptions(client, "cancel"));
  const task = query.data;
  if (query.isError)
    return (
      <p role="alert" className="mt-1 text-xs text-destructive">
        解析状态读取失败{" "}
        <Button size="sm" variant="ghost" onClick={() => void query.refetch()}>
          重试
        </Button>
      </p>
    );
  if (!task) return null;
  const active = ["pending", "processing", "cancel_requested"].includes(task.status);
  return (
    <div className="mt-1 max-w-xs text-xs text-muted-foreground">
      <p aria-live="polite">{processingDescription(task)}</p>
      {task.active_version?.ocr_page_count ? (
        <p>已识别 {task.active_version.ocr_page_count} 个扫描页</p>
      ) : null}
      {task.active_version?.unrecognized_image_count ? (
        <p>包含 {task.active_version.unrecognized_image_count} 张图片，未进行图片语义理解</p>
      ) : null}
      {active ? (
        <Button
          size="sm"
          variant="ghost"
          disabled={
            cancel.isPending || task.status === "cancel_requested" || task.stage === "publishing"
          }
          onClick={() => cancel.mutate({ kb: knowledgeBaseId, file: file.id })}
        >
          取消解析
        </Button>
      ) : !task.requires_ai_consent ? (
        <Button
          size="sm"
          variant="ghost"
          disabled={start.isPending}
          onClick={() => start.mutate({ kb: knowledgeBaseId, file: file.id })}
        >
          {task.status === "succeeded" ? "重新解析" : "重试解析"}
        </Button>
      ) : null}
    </div>
  );
}
