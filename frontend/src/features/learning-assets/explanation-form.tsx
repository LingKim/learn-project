"use client";

import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { userProfileQueryOptions } from "@/features/user-profile/queries";
import type { ExplanationConfig, WeaknessView } from "./api";
import { foundationLabels, depthLabels, sectionLabels } from "./asset-layout";
import { SourcePicker } from "./source-picker";

export const explanationDefaults: ExplanationConfig = {
  topic: "",
  source_mode: "general",
  foundation: "know_concept",
  depth: "systematic",
};

export function ExplanationForm({
  initial,
  selectedWeakness,
  weaknesses,
  pending,
  error,
  onWeaknessChange,
  onDraftChange,
  fixedSource = false,
  onSubmit,
}: {
  initial?: ExplanationConfig;
  selectedWeakness?: WeaknessView | null;
  weaknesses?: WeaknessView[];
  pending: boolean;
  error?: string | null;
  onWeaknessChange?: (id: string) => void;
  onDraftChange?: (config: ExplanationConfig) => void;
  fixedSource?: boolean;
  onSubmit: (config: ExplanationConfig) => void;
}) {
  const [config, setConfig] = useState<ExplanationConfig>(() => ({
    ...explanationDefaults,
    ...initial,
  }));
  const [validation, setValidation] = useState<string | null>(null);
  const profile = useQuery(userProfileQueryOptions());
  const language =
    config.preferred_language === undefined
      ? (profile.data?.preferred_language ?? "zh-CN")
      : config.preferred_language;
  function update(patch: Partial<ExplanationConfig>) {
    setValidation(null);
    const next = { ...config, ...patch };
    setConfig(next);
    onDraftChange?.(next);
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!config.topic?.trim() && !selectedWeakness) {
      setValidation("请输入知识点或选择已有活动难点。");
      return;
    }
    if (config.source_mode === "materials" && !config.knowledge_base_id) {
      setValidation("请选择本人的知识库。");
      return;
    }
    onSubmit({ ...config, topic: config.topic?.trim() ?? "" });
  }
  return (
    <div className="mt-[22px] grid min-w-0 gap-8 xl:grid-cols-[minmax(0,1fr)_330px]">
      <form onSubmit={submit} className="min-w-0 space-y-[18px]">
        <fieldset className="space-y-2">
          <legend className="mb-2 text-sm font-semibold">想精讲的内容</legend>
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              aria-label="知识点"
              value={config.topic ?? ""}
              maxLength={500}
              disabled={pending || fixedSource || Boolean(selectedWeakness)}
              placeholder="输入知识点，如：Spring 事务传播机制"
              onChange={(e) => update({ topic: e.target.value })}
            />
            {onWeaknessChange ? (
              <Select
                value={selectedWeakness?.id ?? "none"}
                disabled={pending}
                onValueChange={(id) => onWeaknessChange(id === "none" ? "" : id)}
              >
                <SelectTrigger aria-label="选择活动难点">
                  <SelectValue placeholder="选择已有活动难点（可选）" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">不关联难点</SelectItem>
                  {weaknesses?.map((item) => (
                    <SelectItem key={item.id} value={item.id}>
                      {item.title}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : null}
          </div>
        </fieldset>
        <fieldset>
          <legend className="mb-2 text-sm font-semibold">当前基础</legend>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {Object.entries(foundationLabels).map(([value, label]) => (
              <Button
                key={value}
                type="button"
                variant={config.foundation === value ? "brand" : "outline"}
                aria-pressed={config.foundation === value}
                disabled={pending}
                onClick={() => update({ foundation: value as ExplanationConfig["foundation"] })}
              >
                {label}
              </Button>
            ))}
          </div>
        </fieldset>
        <fieldset>
          <legend className="mb-2 text-sm font-semibold">期望深度</legend>
          <div className="grid gap-2 sm:grid-cols-3">
            {Object.entries(depthLabels).map(([value, label]) => (
              <Button
                key={value}
                type="button"
                variant={config.depth === value ? "brand" : "outline"}
                aria-pressed={config.depth === value}
                disabled={pending}
                onClick={() => update({ depth: value as ExplanationConfig["depth"] })}
              >
                {label}
              </Button>
            ))}
          </div>
        </fieldset>
        <div className="space-y-1.5">
          <Label>语言</Label>
          <Select
            value={language ?? "none"}
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
        </div>
        <SourcePicker
          config={config}
          onChange={update}
          disabled={pending}
          fixed={fixedSource || Boolean(selectedWeakness)}
        />
        {validation || error || profile.error ? (
          <p role="alert" className="text-sm text-danger">
            {validation ?? error ?? profile.error?.message}
          </p>
        ) : null}
        <div className="flex justify-end gap-3">
          <Button
            type="button"
            variant="outline"
            disabled={pending}
            onClick={() => {
              setConfig(initial ?? explanationDefaults);
              onDraftChange?.(initial ?? explanationDefaults);
              setValidation(null);
            }}
          >
            重置输入
          </Button>
          <Button variant="brand" type="submit" disabled={pending}>
            <Sparkles aria-hidden="true" className="size-4" />
            {pending ? "正在提交…" : "开始精讲"}
          </Button>
        </div>
      </form>
      <aside className="min-w-0 space-y-4" aria-label="本次精讲摘要">
        <h2 className="font-bold">本次精讲将包含</h2>
        <ol className="divide-y divide-border">
          {sectionLabels.map((label, index) => (
            <li key={label} className="flex gap-3 py-3 text-sm">
              <span className="text-accent-foreground">0{index + 1}</span>
              {label}
            </li>
          ))}
        </ol>
        <p className="rounded-lg border border-[#D7E3EA] bg-[#EDF3F7] p-3 text-xs leading-6 text-[#496B86]">
          {config.source_mode === "materials"
            ? "精讲使用明确选择的本人资料；证据不足时保留配置并说明原因。"
            : "本次精讲使用模型通用知识，不引用你的资料。"}
        </p>
      </aside>
    </div>
  );
}
