"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import type { PracticeQuestion } from "./api";

export function QuestionEditor({
  question,
  onClose,
  onSave,
}: {
  question: PracticeQuestion;
  onClose: () => void;
  onSave: (question: PracticeQuestion) => Promise<void>;
}) {
  const [draft, setDraft] = useState(() => structuredClone(question));
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  async function save() {
    setPending(true);
    setError(null);
    try {
      await onSave(draft);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "题目未保存，请检查答案与评分规则。");
    } finally {
      setPending(false);
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !pending) onClose();
      }}
    >
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-[700px]">
        <DialogHeader>
          <DialogTitle>编辑题目</DialogTitle>
          <DialogDescription>修改创建新题集版本，已开始练习的题目不变。</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>题干</Label>
            <Textarea
              aria-label="题干"
              value={draft.stem}
              onChange={(e) => setDraft({ ...draft, stem: e.target.value })}
              disabled={pending}
            />
          </div>
          <div className="space-y-2">
            <Label>知识点（逗号分隔）</Label>
            <Input
              aria-label="题目知识点"
              defaultValue={draft.topics.join(", ")}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  topics: e.target.value
                    .split(/[，,]/)
                    .map((s) => s.trim())
                    .filter(Boolean),
                })
              }
              disabled={pending}
            />
          </div>
          {draft.type === "single_choice" || draft.type === "multiple_choice" ? (
            <fieldset className="space-y-2">
              <legend className="mb-2 text-sm font-semibold">选项（稳定选项编号）</legend>
              {draft.options.map((option) => (
                <label key={option.id} className="flex items-center gap-2 text-sm">
                  {option.id}
                  <Input
                    aria-label={`选项${option.id}`}
                    value={option.text}
                    disabled={pending}
                    onChange={(e) => {
                      if (draft.type === "single_choice" || draft.type === "multiple_choice")
                        setDraft({
                          ...draft,
                          options: draft.options.map((o) =>
                            o.id === option.id ? { ...o, text: e.target.value } : o,
                          ),
                        });
                    }}
                  />
                </label>
              ))}
            </fieldset>
          ) : null}
          <fieldset className="space-y-2">
            <legend className="mb-2 text-sm font-semibold">标准答案</legend>
            {draft.type === "single_choice" ? (
              <Select
                value={draft.answer}
                disabled={pending}
                onValueChange={(answer) => {
                  if (draft.type === "single_choice") setDraft({ ...draft, answer });
                }}
              >
                <SelectTrigger aria-label="标准答案">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {draft.options.map((o) => (
                    <SelectItem key={o.id} value={o.id}>
                      {o.id} · {o.text}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : draft.type === "multiple_choice" ? (
              draft.options.map((o) => (
                <label key={o.id} className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={draft.answer.includes(o.id)}
                    disabled={pending}
                    onCheckedChange={(checked) => {
                      if (draft.type === "multiple_choice")
                        setDraft({
                          ...draft,
                          answer: checked
                            ? [...draft.answer, o.id]
                            : draft.answer.filter((id) => id !== o.id),
                        });
                    }}
                  />
                  {o.id} · {o.text}
                </label>
              ))
            ) : draft.type === "true_false" ? (
              <Select
                value={String(draft.answer)}
                disabled={pending}
                onValueChange={(value) => {
                  if (draft.type === "true_false") setDraft({ ...draft, answer: value === "true" });
                }}
              >
                <SelectTrigger aria-label="判断题标准答案">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="true">正确</SelectItem>
                  <SelectItem value="false">错误</SelectItem>
                </SelectContent>
              </Select>
            ) : (
              <Textarea
                aria-label="标准答案要点"
                defaultValue={draft.answer.join("\n")}
                disabled={pending}
                onChange={(e) => {
                  if (draft.type === "short_answer" || draft.type === "code_text")
                    setDraft({
                      ...draft,
                      answer: e.target.value
                        .split("\n")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    });
                }}
                placeholder="每行一个答案要点"
              />
            )}
          </fieldset>
          <fieldset className="space-y-2">
            <legend className="mb-2 text-sm font-semibold">评分规则</legend>
            {draft.rubric.map((dimension, i) => (
              <div key={dimension.id} className="grid gap-2 sm:grid-cols-[1fr_120px]">
                <Textarea
                  aria-label={`评分维度${i + 1}`}
                  value={dimension.description}
                  disabled={pending}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      rubric: draft.rubric.map((d) =>
                        d.id === dimension.id ? { ...d, description: e.target.value } : d,
                      ),
                    })
                  }
                />
                <Input
                  type="number"
                  aria-label={`评分维度${i + 1}满分`}
                  placeholder="无数值分"
                  value={dimension.max_score ?? ""}
                  min={0.01}
                  max={100}
                  disabled={pending}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      rubric: draft.rubric.map((d) =>
                        d.id === dimension.id
                          ? {
                              ...d,
                              max_score: e.target.value === "" ? null : Number(e.target.value),
                            }
                          : d,
                      ),
                    })
                  }
                />
              </div>
            ))}
          </fieldset>
          <div className="space-y-2">
            <Label>答案讲解</Label>
            <Textarea
              aria-label="答案讲解"
              value={draft.answer_explanation}
              disabled={pending}
              onChange={(e) => setDraft({ ...draft, answer_explanation: e.target.value })}
            />
          </div>
          <p className="text-xs leading-6 text-muted-foreground">
            {draft.source_refs?.length
              ? draft.source_refs
                  .map(
                    (s) =>
                      `资料引用：${s.display_name}${s.page_start ? ` · 第 ${s.page_start} 页` : s.paragraph_start ? ` · 第 ${s.paragraph_start} 段` : ""}`,
                  )
                  .join("；")
              : "模型通用知识"}
            （来源只读，不能伪造或替换引用）
          </p>
          {error ? (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose} disabled={pending}>
              取消
            </Button>
            <Button
              variant="brand"
              onClick={() => {
                void save();
              }}
              disabled={pending}
            >
              {pending ? "校验并保存…" : "保存新版本"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
