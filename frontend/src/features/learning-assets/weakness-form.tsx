"use client";

import { useState, type FormEvent } from "react";
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
import type { WeaknessCreate, WeaknessPatch, WeaknessView, ExplanationConfig } from "./api";
import { severityLabels } from "./asset-layout";
import { SourcePicker } from "./source-picker";

export function WeaknessForm({
  initial,
  pending,
  error,
  onSubmit,
  onCancel,
}: {
  initial?: WeaknessView;
  pending: boolean;
  error?: string | null;
  onSubmit: (data: Omit<WeaknessCreate, "request_key"> | WeaknessPatch) => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [domain, setDomain] = useState(initial?.domain ?? "");
  const [tags, setTags] = useState(initial?.tags.join(", ") ?? "");
  const [severity, setSeverity] = useState<WeaknessCreate["severity"]>(
    initial?.severity ?? "medium",
  );
  const [source, setSource] = useState<ExplanationConfig>(() => ({
    source_mode: initial?.source_mode ?? "general",
    knowledge_base_id: initial?.knowledge_base_id ?? null,
    file_ids: initial?.file_ids ?? [],
  }));
  const [validation, setValidation] = useState<string | null>(null);
  function submit(event: FormEvent) {
    event.preventDefault();
    const parsedTags = tags
      .split(/[,，\n]/)
      .map((tag) => tag.trim())
      .filter(Boolean);
    if (!title.trim()) {
      setValidation("请输入难点名称。");
      return;
    }
    if (parsedTags.length > 20 || parsedTags.some((tag) => tag.length > 60)) {
      setValidation("最多 20 个标签，每个最多 60 字。");
      return;
    }
    if (source.source_mode === "materials" && !source.knowledge_base_id) {
      setValidation("请选择本人的知识库。");
      return;
    }
    const fields = {
      title: title.trim(),
      domain: domain.trim() || null,
      tags: parsedTags,
      severity,
    };
    onSubmit(
      initial
        ? { ...fields, expected_version: initial.version }
        : {
            ...fields,
            source_mode: source.source_mode,
            knowledge_base_id: source.knowledge_base_id,
            file_ids: source.file_ids,
          },
    );
  }
  return (
    <form onSubmit={submit} className="min-w-0 space-y-4">
      <div className="space-y-1.5">
        <Label>难点名称</Label>
        <Input
          aria-label="难点名称"
          value={title}
          maxLength={120}
          disabled={pending}
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label>领域</Label>
          <Input
            aria-label="领域"
            value={domain}
            maxLength={120}
            disabled={pending}
            onChange={(e) => setDomain(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label>严重度</Label>
          <Select
            value={severity}
            disabled={pending}
            onValueChange={(value) => {
              if (value === "low" || value === "medium" || value === "high") setSeverity(value);
            }}
          >
            <SelectTrigger aria-label="严重度">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(severityLabels).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="space-y-1.5">
        <Label>标签</Label>
        <Input
          aria-label="标签"
          value={tags}
          placeholder="使用逗号分隔"
          disabled={pending}
          onChange={(e) => setTags(e.target.value)}
        />
      </div>
      <SourcePicker
        config={source}
        disabled={pending}
        fixed={Boolean(initial)}
        onChange={(patch) => setSource((old) => ({ ...old, ...patch }))}
      />
      {!initial ? (
        <p className="text-xs leading-6 text-muted-foreground">
          手动创建表示你主动选择学习这个概念，并非系统诊断或掌握证明。
        </p>
      ) : null}
      {validation || error ? (
        <p role="alert" className="text-sm text-danger">
          {validation ?? error}
        </p>
      ) : null}
      <div className="flex justify-end gap-3">
        <Button variant="outline" type="button" disabled={pending} onClick={onCancel}>
          取消
        </Button>
        <Button variant="brand" type="submit" disabled={pending}>
          {pending ? "正在保存…" : initial ? "保存修改" : "创建难点"}
        </Button>
      </div>
    </form>
  );
}
