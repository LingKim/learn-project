"use client";

import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { userProfileQueryOptions } from "@/features/user-profile/queries";
import {
  knowledgeBaseListQueryOptions,
  knowledgeFileListQueryOptions,
} from "@/features/file-management/queries";
import type { PracticeConfig, PracticeQuestion } from "./api";

export const questionLabels: Record<PracticeQuestion["type"], string> = {
  single_choice: "单选题",
  multiple_choice: "多选题",
  true_false: "判断题",
  short_answer: "简答题",
  code_text: "文本编程题",
};
export const difficultyLabels = { easy: "简单", medium: "中等", hard: "困难" };
const defaults: PracticeConfig = {
  mode: "practice",
  source_mode: "general",
  topic: "",
  difficulty: "medium",
  question_count: 5,
  question_types: { single_choice: 5 },
};
const levels = {
  intern: "实习",
  junior: "初级",
  intermediate: "中级",
  senior: "高级",
  expert: "专家",
};
function list(value: string) {
  return value
    .split(/[，,\n]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function ConfigForm({
  initial,
  title = "学习练习",
  fixedSource = false,
  pending,
  error,
  onConfirm,
}: {
  initial?: PracticeConfig;
  title?: string;
  fixedSource?: boolean;
  pending: boolean;
  error: string | null;
  onConfirm: (config: PracticeConfig, title: string) => void;
}) {
  const [config, setConfig] = useState<PracticeConfig>(() => initial ?? defaults);
  const [name, setName] = useState(title);
  const [skillsInput, setSkillsInput] = useState<string | null>(null);
  const [focusInput, setFocusInput] = useState<string | null>(null);
  const [validation, setValidation] = useState<string | null>(null);
  const profile = useQuery(userProfileQueryOptions());
  const bases = useQuery(knowledgeBaseListQueryOptions(1, 100));
  const files = useQuery({
    ...knowledgeFileListQueryOptions(config.knowledge_base_id ?? "", 1, 100),
    enabled: config.source_mode === "materials" && Boolean(config.knowledge_base_id),
  });
  function update(patch: Partial<PracticeConfig>) {
    setValidation(null);
    setConfig((old) => ({ ...old, ...patch }));
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    const counts = Object.values(config.question_types ?? {});
    if (
      counts.some((n) => !Number.isInteger(n) || n < 0) ||
      counts.reduce((a, b) => a + b, 0) !== config.question_count ||
      !config.question_count ||
      config.question_count < 1 ||
      config.question_count > 20
    ) {
      setValidation("各题型数量之和应等于题量，题量为 1–20。");
      return;
    }
    if (!name.trim()) {
      setValidation("请输入练习名称。");
      return;
    }
    if (config.source_mode === "materials" && !config.knowledge_base_id) {
      setValidation("请选择本人的知识库。");
      return;
    }
    onConfirm(config, name.trim());
  }
  const targetJob =
    config.target_job === undefined ? (profile.data?.target_job ?? "") : (config.target_job ?? "");
  const skills =
    config.target_skills === undefined
      ? (profile.data?.target_skills ?? [])
      : (config.target_skills ?? []);
  return (
    <div className="mt-[18px] grid min-w-0 gap-[30px] xl:grid-cols-[minmax(0,1fr)_300px]">
      <form onSubmit={submit} className="grid min-w-0 content-start gap-[14px] sm:grid-cols-2">
        {config.learning_target ? (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-sidebar p-3 text-xs sm:col-span-2">
            <p>关联学习目标：{initial?.topic}。调整知识点或资料范围前可取消关联。</p>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={pending}
              onClick={() => update({ learning_target: null })}
            >
              取消关联
            </Button>
          </div>
        ) : null}
        <Field label="练习名称">
          <Input
            aria-label="练习名称"
            value={name}
            maxLength={120}
            onChange={(e) => setName(e.target.value)}
            disabled={pending}
          />
        </Field>
        <Field label="知识点">
          <Input
            aria-label="知识点"
            value={config.topic ?? ""}
            onChange={(e) => update({ topic: e.target.value })}
            placeholder="输入本次练习的知识点"
            disabled={pending}
          />
        </Field>
        <Field label="目标岗位">
          <Input
            aria-label="目标岗位"
            value={targetJob}
            placeholder="使用个人画像，可显式清空"
            onChange={(e) => update({ target_job: e.target.value.trim() || null })}
            disabled={pending}
          />
        </Field>
        <Field label="技术栈">
          <Input
            aria-label="技术栈"
            value={skillsInput ?? skills.join(", ")}
            placeholder="逗号分隔"
            onChange={(e) => {
              setSkillsInput(e.target.value);
              update({ target_skills: list(e.target.value) });
            }}
            disabled={pending}
          />
        </Field>
        <Field label="知识来源">
          <Select
            value={config.source_mode ?? "general"}
            onValueChange={(value) => {
              if (value === "materials" || value === "general")
                update({ source_mode: value, knowledge_base_id: null, file_ids: [] });
            }}
            disabled={fixedSource || pending}
          >
            <SelectTrigger aria-label="知识来源">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="materials">资料模式</SelectItem>
              <SelectItem value="general">模型通用知识</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        {config.source_mode === "materials" ? (
          <Field label="出题资料">
            <Select
              value={config.knowledge_base_id ?? ""}
              disabled={fixedSource || pending}
              onValueChange={(value) => update({ knowledge_base_id: value, file_ids: [] })}
            >
              <SelectTrigger aria-label="出题资料">
                <SelectValue placeholder="选择知识库" />
              </SelectTrigger>
              <SelectContent>
                {bases.data?.data.map((b) => (
                  <SelectItem value={b.id} key={b.id}>
                    {b.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        ) : (
          <p className="self-end py-3 text-xs text-muted-foreground">
            本次使用模型通用知识，不引用个人资料。
          </p>
        )}
        {config.source_mode === "materials" && config.knowledge_base_id ? (
          <fieldset className="space-y-2 sm:col-span-2">
            <legend className="mb-2 text-xs font-semibold">
              文件范围（未选择时使用知识库内有效资料）
            </legend>
            {files.isPending ? (
              <p role="status" className="text-xs">
                正在读取文件…
              </p>
            ) : null}
            {files.error ? (
              <p role="alert" className="text-xs text-danger">
                {files.error.message}
              </p>
            ) : null}
            {files.data?.data.map((file) => (
              <label key={file.id} className="flex items-center gap-2 text-xs">
                <Checkbox
                  checked={(config.file_ids ?? []).includes(file.id)}
                  disabled={fixedSource || pending}
                  onCheckedChange={(checked) =>
                    update({
                      file_ids: checked
                        ? [...(config.file_ids ?? []), file.id]
                        : (config.file_ids ?? []).filter((id) => id !== file.id),
                    })
                  }
                />
                {file.display_name}
              </label>
            ))}
          </fieldset>
        ) : null}
        <Field label="难度">
          <Select
            value={config.difficulty ?? "medium"}
            disabled={pending}
            onValueChange={(value) => {
              if (value === "easy" || value === "medium" || value === "hard")
                update({ difficulty: value });
            }}
          >
            <SelectTrigger aria-label="难度">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(difficultyLabels).map(([key, label]) => (
                <SelectItem value={key} key={key}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field label="题量">
          <Input
            type="number"
            aria-label="题量"
            min={1}
            max={20}
            value={config.question_count ?? 5}
            onChange={(e) => update({ question_count: Number(e.target.value) })}
            disabled={pending}
          />
        </Field>
        <fieldset className="sm:col-span-2">
          <legend className="mb-2 text-xs font-semibold">题型与各类题量</legend>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {Object.entries(questionLabels).map(([type, label]) => (
              <Field label={label} key={type}>
                <Input
                  type="number"
                  min={0}
                  max={20}
                  aria-label={`${label}数量`}
                  value={config.question_types?.[type] ?? 0}
                  onChange={(e) =>
                    update({
                      question_types: { ...config.question_types, [type]: Number(e.target.value) },
                    })
                  }
                  disabled={pending}
                />
              </Field>
            ))}
          </div>
        </fieldset>
        <Field label="目标能力">
          <Input
            aria-label="目标能力"
            value={
              config.learning_goal === undefined
                ? (profile.data?.learning_goal ?? "")
                : (config.learning_goal ?? "")
            }
            onChange={(e) => update({ learning_goal: e.target.value.trim() || null })}
            disabled={pending}
          />
        </Field>
        <Field label="语言">
          <Select
            value={
              config.preferred_language === undefined
                ? (profile.data?.preferred_language ?? "zh-CN")
                : (config.preferred_language ?? "none")
            }
            disabled={pending}
            onValueChange={(value) => {
              if (value === "zh-CN" || value === "en-US" || value === "none")
                update({ preferred_language: value === "none" ? null : value });
            }}
          >
            <SelectTrigger aria-label="语言">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="zh-CN">中文</SelectItem>
              <SelectItem value="en-US">English</SelectItem>
              <SelectItem value="none">本次不使用画像语言</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <Field label="工作月数">
          <Input
            type="number"
            min={0}
            max={720}
            aria-label="工作月数"
            value={
              config.experience_months === undefined
                ? (profile.data?.experience_months ?? "")
                : (config.experience_months ?? "")
            }
            onChange={(e) =>
              update({ experience_months: e.target.value === "" ? null : Number(e.target.value) })
            }
            disabled={pending}
          />
        </Field>
        <Field label="岗位等级">
          <Select
            value={
              config.target_level === undefined
                ? (profile.data?.target_level ?? "none")
                : (config.target_level ?? "none")
            }
            disabled={pending}
            onValueChange={(value) => {
              if (value === "none" || value in levels)
                update({
                  target_level:
                    value === "none"
                      ? null
                      : (value as NonNullable<PracticeConfig["target_level"]>),
                });
            }}
          >
            <SelectTrigger aria-label="岗位等级">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">本次不使用岗位等级</SelectItem>
              {Object.entries(levels).map(([key, label]) => (
                <SelectItem value={key} key={key}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field label="关注知识点">
          <Input
            aria-label="关注知识点"
            value={
              focusInput ??
              (config.focus_topics === undefined
                ? (profile.data?.focus_topics ?? [])
                : (config.focus_topics ?? [])
              ).join(", ")
            }
            onChange={(e) => {
              setFocusInput(e.target.value);
              update({ focus_topics: list(e.target.value) });
            }}
            disabled={pending}
          />
        </Field>
        {fixedSource ? (
          <p className="self-end py-3 text-xs text-muted-foreground">
            切换资料来源或文件范围，请新建练习。
          </p>
        ) : null}
        {validation || error || bases.error || profile.error ? (
          <p role="alert" className="text-sm text-danger sm:col-span-2">
            {validation ?? error ?? bases.error?.message ?? profile.error?.message}
          </p>
        ) : null}
        <div className="flex justify-end sm:col-span-2">
          <Button variant="brand" disabled={pending} type="submit">
            <Sparkles aria-hidden="true" className="size-4" />
            {pending ? "正在保存配置…" : "生成题目方案"}
          </Button>
        </div>
      </form>
      <aside className="min-w-0 space-y-[14px]" aria-label="本次练习摘要">
        <h2 className="text-base font-bold">本次练习</h2>
        <dl className="border-t border-border">
          {[
            ["岗位", targetJob || "未设置"],
            ["难度", difficultyLabels[config.difficulty ?? "medium"]],
            ["题量", `${config.question_count ?? 5} 题`],
            ["练习", "不计时"],
            ["来源", config.source_mode === "materials" ? "本人资料" : "模型通用知识"],
          ].map(([label, value]) => (
            <div
              key={label}
              className="flex min-h-[42px] justify-between gap-3 border-b border-border py-3 text-xs"
            >
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="min-w-0 break-words text-right font-semibold">{value}</dd>
            </div>
          ))}
        </dl>
        <p className="rounded-lg border border-[#D7E3EA] bg-[#EDF3F7] p-3 text-xs leading-6 text-[#496B86]">
          AI 提供配置建议；确认后才生成题目。默认画像仅用于本次配置，不自动修改个人资料。
        </p>
      </aside>
    </div>
  );
}
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0 space-y-1.5">
      <Label className="text-xs font-semibold">{label}</Label>
      {children}
    </div>
  );
}
