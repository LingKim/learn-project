"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleCheck, RotateCcw, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { DeleteRequest } from "./api";
import {
  knowledgeBaseDeletionImpactQueryOptions,
  knowledgeFileDeletionImpactQueryOptions,
} from "./queries";

type DeleteImpactDialogProps = {
  kind: "knowledge-base" | "file";
  open: boolean;
  name: string;
  knowledgeBaseId: string;
  knowledgeFileId?: string;
  mode: NonNullable<DeleteRequest["mode"]>;
  pending: boolean;
  onModeChange: (mode: NonNullable<DeleteRequest["mode"]>) => void;
  onOpenChange: (open: boolean) => void;
  onConfirm: (confirmationToken: string) => void;
};

const impactItems = [
  ["conversations", "会话"],
  ["questions", "题目"],
  ["reports", "报告"],
  ["notes", "笔记"],
  ["weaknesses", "难点"],
] as const;

export function DeleteImpactDialog({
  kind,
  open,
  name,
  knowledgeBaseId,
  knowledgeFileId = "",
  mode,
  pending,
  onModeChange,
  onOpenChange,
  onConfirm,
}: DeleteImpactDialogProps) {
  const knowledgeBaseQuery = useQuery(
    knowledgeBaseDeletionImpactQueryOptions(
      kind === "knowledge-base" && open ? knowledgeBaseId : "",
      mode,
    ),
  );
  const fileQuery = useQuery(
    knowledgeFileDeletionImpactQueryOptions(
      kind === "file" && open ? knowledgeBaseId : "",
      kind === "file" && open ? knowledgeFileId : "",
      mode,
    ),
  );
  const query = kind === "knowledge-base" ? knowledgeBaseQuery : fileQuery;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>确认删除“{name}”</DialogTitle>
          <DialogDescription>
            默认仅删除来源，已有业务内容继续保留并标记来源已删除。确认信息具有短时效，提交前会使用刚刚获取的令牌。
          </DialogDescription>
        </DialogHeader>

        {query.isPending ? (
          <p
            className="rounded-md bg-muted px-4 py-5 text-sm text-muted-foreground"
            aria-busy="true"
          >
            正在计算删除影响…
          </p>
        ) : query.isError ? (
          <p
            role="alert"
            className="rounded-md bg-[color-mix(in_oklch,var(--danger)_10%,var(--surface))] px-4 py-3 text-sm text-danger"
          >
            {query.error.message}
          </p>
        ) : (
          <div className="grid grid-cols-2 border-y border-border sm:grid-cols-5">
            {impactItems.map(([key, label]) => (
              <div key={key} className="border-border px-4 py-3 sm:border-r sm:last:border-r-0">
                <p className="text-xl font-bold">{query.data?.[key] ?? 0}</p>
                <p className="mt-1 text-xs text-muted-foreground">{label}</p>
              </div>
            ))}
          </div>
        )}

        <fieldset className="grid gap-2">
          <legend className="mb-1 text-sm font-semibold">选择删除范围</legend>
          <button
            type="button"
            onClick={() => onModeChange("SOURCE_ONLY")}
            className={`flex items-start gap-3 rounded-md border p-4 text-left transition-colors ${
              mode === "SOURCE_ONLY" ? "border-primary bg-primary/20" : "border-border bg-surface"
            }`}
          >
            <CircleCheck className="mt-0.5 size-4 shrink-0 text-accent-foreground" />
            <span>
              <span className="block text-sm font-semibold">仅删除来源（推荐）</span>
              <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                保留会话、题目、报告、笔记和难点，只解除当前来源关联。
              </span>
            </span>
          </button>
          <button
            type="button"
            onClick={() => onModeChange("CASCADE")}
            className={`flex items-start gap-3 rounded-md border p-4 text-left transition-colors ${
              mode === "CASCADE" ? "border-primary bg-primary/20" : "border-border bg-surface"
            }`}
          >
            <span className="mt-0.5 size-4 shrink-0 rounded-full border border-muted-foreground" />
            <span>
              <span className="block text-sm font-semibold">级联删除相关内容</span>
              <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                同时删除上方受影响内容；当前版本没有前端恢复入口，请谨慎选择。
              </span>
            </span>
          </button>
        </fieldset>

        <div className="flex gap-2 rounded-md bg-muted px-4 py-3 text-xs leading-5 text-muted-foreground">
          <RotateCcw className="mt-0.5 size-4 shrink-0" />
          最后一个有效知识库会被后端阻止删除；默认知识库可以重命名，但仍受最后知识库保护。
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            type="button"
            variant="brand"
            disabled={!query.data || pending}
            onClick={() => query.data && onConfirm(query.data.confirmation_token)}
          >
            <Trash2 />
            {pending ? "正在删除" : mode === "SOURCE_ONLY" ? "删除来源" : "确认级联删除"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
