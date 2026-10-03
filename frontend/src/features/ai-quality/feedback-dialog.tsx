"use client";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link2, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { CheckboxField } from "@/components/ui/checkbox-field";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { useAuth } from "@/features/auth/auth-provider";
import { createCaseMutationOptions } from "./queries";
import type { CaseCreate } from "./api";
import { categories, ErrorNotice } from "./common";
import { cn } from "@/lib/utils";

type FeedbackProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sourceId: string;
  traceId: string;
  onCreated?: (id: string) => void;
};
export function QualityFeedbackDialog(props: FeedbackProps) {
  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className="max-w-[680px] gap-5 p-7">
        {props.open && <FeedbackForm key={`${props.sourceId}:${props.traceId}`} {...props} />}
      </DialogContent>
    </Dialog>
  );
}
function FeedbackForm({ sourceId, traceId, onOpenChange, onCreated }: FeedbackProps) {
  const { user } = useAuth();
  const client = useQueryClient();
  const active = useRef(true);
  const create = useMutation(createCaseMutationOptions(client, () => active.current));
  const [category, setCategory] = useState<CaseCreate["category"] | "">("");
  const [description, setDescription] = useState("");
  const [expected, setExpected] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [requestKey] = useState(() => crypto.randomUUID());
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!category || !description.trim() || !confirmed || create.isPending || user?.role !== "user")
      return;
    try {
      // request_key 在本次弹窗重试期间保持一致，避免网络重试产生重复反馈。
      const result = await create.mutateAsync({
        source_type: "learning_turn",
        source_id: sourceId,
        trace_id: traceId,
        request_key: requestKey,
        category,
        description: description.trim(),
        expected_result: expected.trim() || null,
        basic_access_confirmed: true,
      });
      if (!active.current) return;
      onOpenChange(false);
      onCreated?.(result.data.id);
    } catch {
      /* 统一 Mutation 错误同时留在当前表单中，保留未提交草稿供用户修正。 */
    }
  }
  return (
    <form onSubmit={submit} className="grid gap-5">
      <DialogHeader>
        <DialogTitle className="text-[22px] leading-tight">这次回答哪里需要改进？</DialogTitle>
        <DialogDescription>
          我们会把这次回答和资料引用来源一起提交，方便管理员准确定位问题。
        </DialogDescription>
      </DialogHeader>
      <div className="flex items-center gap-2 rounded-lg bg-sky-50 px-3 py-3 text-xs text-sky-900">
        <Link2 className="size-4 shrink-0" />
        仅关联本次资料问答
      </div>
      <fieldset>
        <legend className="mb-2 text-sm">问题类型 *</legend>
        <div className="flex max-w-[400px] flex-wrap gap-2">
          {Object.entries(categories).map(([value, label]) => (
            <label key={value} className="cursor-pointer">
              <input
                className="peer sr-only"
                type="radio"
                name="quality-category"
                value={value}
                checked={category === value}
                onChange={() => setCategory(value as CaseCreate["category"])}
              />
              <span
                className={cn(
                  "inline-flex min-h-9 items-center rounded-md border px-3 text-xs peer-focus-visible:outline-2 peer-focus-visible:outline-primary",
                  category === value ? "border-primary bg-primary/15" : "border-border",
                )}
              >
                {label}
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      <label className="grid gap-2 text-sm">
        问题描述 *
        <Textarea
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          maxLength={4000}
          required
          className="min-h-[94px]"
          placeholder="请说明实际回答与期望之间的差异…"
        />
      </label>
      <label className="grid gap-2 text-sm">
        期望结果（选填）
        <Input
          className="h-11"
          value={expected}
          onChange={(event) => setExpected(event.target.value)}
          maxLength={2000}
          placeholder="例如：希望优先回答资料中的相关章节"
        />
      </label>
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
        <CheckboxField
          label="我同意管理员查看这一次请求的必要信息"
          checked={confirmed}
          onCheckedChange={(value) => setConfirmed(value === true)}
        />
        <p className="mt-2 text-xs leading-5 text-muted-foreground">
          用于本次问题诊断：管理员可查看本次问题、AI 回答、最终引用和链路元数据，最长 30
          天或工单关闭时失效。不可查看整份文件、同会话其他内容或原文件下载；候选片段需要再次向你申请。可随时撤销正文授权。
        </p>
      </div>
      {create.error && <ErrorNotice error={create.error} />}
      {user?.role !== "user" && (
        <p role="alert" className="text-sm text-destructive">
          请使用本人学习账号提交反馈。
        </p>
      )}
      <DialogFooter>
        <span className="mr-auto self-center text-xs text-muted-foreground">
          {description.length} / 4000
        </span>
        <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
          取消
        </Button>
        <Button
          type="submit"
          variant="brand"
          disabled={
            !category ||
            !description.trim() ||
            !confirmed ||
            create.isPending ||
            !sourceId ||
            !traceId ||
            user?.role !== "user"
          }
        >
          <Send className="size-4" />
          {create.isPending ? "正在提交…" : "提交反馈"}
        </Button>
      </DialogFooter>
    </form>
  );
}
