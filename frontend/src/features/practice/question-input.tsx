"use client";

import { cn } from "@/lib/utils";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Textarea } from "@/components/ui/textarea";
import type { PracticeAnswer, PracticeQuestion } from "./api";

export function QuestionInput({
  question,
  value,
  onChange,
  disabled,
}: {
  question: PracticeQuestion;
  value?: PracticeAnswer;
  onChange: (value: PracticeAnswer) => void;
  disabled: boolean;
}) {
  if (question.type === "single_choice")
    return (
      <RadioGroup
        aria-label="单选答案"
        value={value?.type === "single_choice" ? value.option_id : ""}
        onValueChange={(option_id) => onChange({ type: "single_choice", option_id })}
        disabled={disabled}
        className="space-y-2"
      >
        {question.options.map((o) => (
          <Label
            key={o.id}
            className={cn(
              "flex min-h-11 cursor-pointer items-center gap-3 rounded-md border border-border p-3 text-sm",
              value?.type === "single_choice" && value.option_id === o.id
                ? "bg-muted"
                : "bg-surface",
            )}
          >
            <RadioGroupItem value={o.id} id={`${question.question_id}-${o.id}`} />
            {o.id} · {o.text}
          </Label>
        ))}
      </RadioGroup>
    );
  if (question.type === "multiple_choice") {
    const selected = value?.type === "multiple_choice" ? value.option_ids : [];
    return (
      <fieldset aria-label="多选答案" className="space-y-2">
        {question.options.map((o) => (
          <Label
            key={o.id}
            className={cn(
              "flex min-h-11 cursor-pointer items-center gap-3 rounded-md border border-border p-3 text-sm",
              selected.includes(o.id) ? "bg-muted" : "bg-surface",
            )}
          >
            <Checkbox
              checked={selected.includes(o.id)}
              disabled={disabled}
              onCheckedChange={(checked) =>
                onChange({
                  type: "multiple_choice",
                  option_ids: checked ? [...selected, o.id] : selected.filter((id) => id !== o.id),
                })
              }
            />
            {o.id} · {o.text}
          </Label>
        ))}
        <p className="text-xs text-muted-foreground">多选按完全匹配判分，选项顺序不影响结果。</p>
      </fieldset>
    );
  }
  if (question.type === "true_false")
    return (
      <RadioGroup
        aria-label="判断答案"
        value={value?.type === "true_false" ? String(value.value) : ""}
        onValueChange={(answer) => onChange({ type: "true_false", value: answer === "true" })}
        disabled={disabled}
        className="grid grid-cols-2 gap-3"
      >
        {[
          ["true", "正确"],
          ["false", "错误"],
        ].map(([answer, label]) => (
          <Label
            key={answer}
            className={cn(
              "flex min-h-11 cursor-pointer items-center gap-3 rounded-md border border-border p-3 text-sm",
              value?.type === "true_false" && String(value.value) === answer
                ? "bg-muted"
                : "bg-surface",
            )}
          >
            <RadioGroupItem value={answer} />
            {label}
          </Label>
        ))}
      </RadioGroup>
    );
  const text = value?.type === "short_answer" || value?.type === "code_text" ? value.text : "";
  return (
    <div className="space-y-2">
      <Textarea
        aria-label={question.type === "code_text" ? "代码文本答案" : "简答答案"}
        className={`min-h-[280px] bg-surface leading-7 ${question.type === "code_text" ? "font-mono text-sm" : ""}`}
        value={text}
        disabled={disabled}
        onChange={(e) => onChange({ type: question.type, text: e.target.value })}
        placeholder={
          question.type === "code_text" ? "输入代码与思路，本次不执行代码" : "输入您的回答"
        }
      />
      <div className="flex flex-wrap justify-between gap-2 text-xs text-muted-foreground">
        <span>已输入 {text.length} 字</span>
        <span>
          {question.type === "code_text" ? "仅评价代码文本，不执行代码" : "支持 Markdown 与代码块"}
        </span>
      </div>
    </div>
  );
}
