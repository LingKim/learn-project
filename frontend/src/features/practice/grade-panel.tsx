"use client";

import { useState, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { AnswerContent } from "@/features/learning/answer-content";
import type { GradeView, FeedbackRequest, PracticeAnswer } from "./api";
import { practiceFeedbackOptions, practiceKeys } from "./queries";

export const gradeLabels = {
  correct: "正确",
  partial: "部分正确",
  incorrect: "错误",
  absent: "缺失",
  ungraded: "未评分",
  unsubmitted: "未提交",
};
export function answerText(answer: PracticeAnswer) {
  if (answer.type === "single_choice") return answer.option_id;
  if (answer.type === "multiple_choice") return answer.option_ids.join(", ");
  if (answer.type === "true_false") return answer.value ? "正确" : "错误";
  return answer.text;
}
export function FeedbackButtons({
  target,
  value = null,
}: {
  target: Omit<FeedbackRequest, "feedback">;
  value?: FeedbackRequest["feedback"];
}) {
  const client = useQueryClient();
  const mutation = useMutation(practiceFeedbackOptions());
  const [saved, setSaved] = useState<FeedbackRequest["feedback"]>(value);
  useEffect(() => {
    setSaved(value);
  }, [value]);
  async function choose(next: "helpful" | "unhelpful") {
    try {
      const result = await mutation.mutateAsync({
        ...target,
        feedback: saved === next ? null : next,
      });
      setSaved(result.data.feedback);
      await client.invalidateQueries({ queryKey: practiceKeys.all });
    } catch {
      /* Mutation error is rendered locally. */
    }
  }
  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        {(
          [
            ["helpful", "有帮助", ThumbsUp],
            ["unhelpful", "无帮助", ThumbsDown],
          ] as const
        ).map(([value, label, Icon]) => (
          <Button
            key={value}
            type="button"
            size="sm"
            variant={saved === value ? "brand" : "outline"}
            aria-label={label}
            title={label}
            aria-pressed={saved === value}
            disabled={mutation.isPending}
            onClick={() => {
              void choose(value);
            }}
          >
            <Icon aria-hidden="true" className="size-4" />
          </Button>
        ))}
      </div>
      {mutation.error ? (
        <p role="alert" className="text-xs text-danger">
          {mutation.error.message}
        </p>
      ) : null}
    </div>
  );
}
export function GradePanel({
  grade,
  code = false,
  subjective,
  onRegrade,
  feedback,
}: {
  grade: GradeView;
  code?: boolean;
  subjective: boolean;
  onRegrade?: (reason: string) => Promise<void>;
  feedback?: FeedbackRequest["feedback"];
}) {
  const [reason, setReason] = useState("");
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function regrade() {
    if (!onRegrade || !reason.trim()) return;
    setPending(true);
    setError(null);
    try {
      await onRegrade(reason.trim());
      setOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "重评请求未完成");
    } finally {
      setPending(false);
    }
  }
  return (
    <section
      aria-label={`点评版本${grade.version}`}
      className="space-y-4 rounded-lg border border-border bg-muted p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-lg font-semibold">本题点评 · {gradeLabels[grade.level]}</h3>
        <p className="text-xs">
          点评 v{grade.version}
          {grade.score != null && grade.max_score != null
            ? ` · ${grade.score} / ${grade.max_score} 分`
            : ""}
        </p>
      </div>
      {subjective ? (
        <p className="text-xs text-muted-foreground">
          模型自报置信度 {grade.confidence.toFixed(2)}，不代表校准概率。
          {grade.low_confidence ? "低置信度，建议核对证据或重新评分。" : ""}
        </p>
      ) : null}
      {code ? (
        <p className="text-xs text-muted-foreground">仅评价代码文本，本次不执行代码。</p>
      ) : null}
      <div className="space-y-3">
        {grade.dimensions.map((dimension) => (
          <div key={dimension.dimension_id} className="border-t border-border pt-3">
            <p className="text-sm font-semibold">
              {grade.rubric.find((r) => r.id === dimension.dimension_id)?.description ??
                dimension.dimension_id}{" "}
              · {gradeLabels[dimension.level]}
            </p>
            {dimension.evidence?.map((e, index) => (
              <blockquote
                key={`${e.start}:${e.end}:${index}`}
                className="mt-2 border-l-2 border-primary pl-3 text-sm leading-6"
              >
                回答证据：“{e.quote}”
                <span className="ml-2 text-xs text-muted-foreground">
                  位置 {e.start}–{e.end}
                </span>
              </blockquote>
            ))}
            {dimension.level === "absent" ? (
              <p className="mt-2 text-xs text-muted-foreground">回答中未找到该要点的证据。</p>
            ) : null}
          </div>
        ))}
      </div>
      {(grade.error_reasons ?? []).length ? (
        <div>
          <h4 className="mb-1 text-sm font-semibold">错误原因</h4>
          {grade.error_reasons?.map((s, i) => (
            <AnswerContent key={i} content={s} />
          ))}
        </div>
      ) : null}
      {(grade.missing_points ?? []).length ? (
        <div>
          <h4 className="mb-1 text-sm font-semibold">缺失要点</h4>
          {grade.missing_points?.map((s, i) => (
            <AnswerContent key={i} content={s} />
          ))}
        </div>
      ) : null}
      {(grade.suggestions ?? []).length ? (
        <div>
          <h4 className="mb-1 text-sm font-semibold">改进建议</h4>
          {grade.suggestions?.map((s, i) => (
            <AnswerContent key={i} content={s} />
          ))}
        </div>
      ) : null}
      <p className="text-xs text-muted-foreground">
        {grade.source_mode === "general" ? "模型通用知识" : "本人资料"} · {grade.topics.join(" / ")}
      </p>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <FeedbackButtons
          key={grade.id}
          target={{ grade_id: grade.id }}
          value={feedback ?? grade.feedback}
        />
        {subjective && onRegrade ? (
          <Button type="button" size="sm" variant="outline" onClick={() => setOpen(true)}>
            重新评分
          </Button>
        ) : null}
      </div>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>重新评分</DialogTitle>
            <DialogDescription>新点评会保留旧版本，请说明希望复核的原因。</DialogDescription>
          </DialogHeader>
          <Textarea
            aria-label="重评原因"
            value={reason}
            maxLength={1000}
            onChange={(e) => setReason(e.target.value)}
            disabled={pending}
          />
          {error ? (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          ) : null}
          <Button
            variant="brand"
            disabled={pending || !reason.trim()}
            onClick={() => {
              void regrade();
            }}
          >
            {pending ? "正在请求重评…" : "确认重评"}
          </Button>
        </DialogContent>
      </Dialog>
    </section>
  );
}
