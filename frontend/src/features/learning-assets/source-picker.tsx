"use client";

import { useQuery } from "@tanstack/react-query";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  knowledgeBaseListQueryOptions,
  knowledgeFileListQueryOptions,
} from "@/features/file-management/queries";
import type { ExplanationConfig } from "./api";

export function SourcePicker({
  config,
  disabled = false,
  fixed = false,
  onChange,
}: {
  config: ExplanationConfig;
  disabled?: boolean;
  fixed?: boolean;
  onChange: (patch: Partial<ExplanationConfig>) => void;
}) {
  const bases = useQuery(knowledgeBaseListQueryOptions(1, 100));
  const files = useQuery({
    ...knowledgeFileListQueryOptions(config.knowledge_base_id ?? "", 1, 100),
    enabled: config.source_mode === "materials" && Boolean(config.knowledge_base_id),
  });
  return (
    <fieldset className="min-w-0 space-y-3">
      <legend className="mb-2 text-sm font-semibold">知识来源</legend>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label>知识来源模式</Label>
          <Select
            value={config.source_mode ?? "general"}
            disabled={disabled || fixed}
            onValueChange={(value) => {
              if (value === "general" || value === "materials")
                onChange({ source_mode: value, knowledge_base_id: null, file_ids: [] });
            }}
          >
            <SelectTrigger aria-label="知识来源模式">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="general">通用模式</SelectItem>
              <SelectItem value="materials">资料模式</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {config.source_mode === "materials" ? (
          <div className="space-y-1.5">
            <Label>知识库</Label>
            <Select
              value={config.knowledge_base_id ?? ""}
              disabled={disabled || fixed}
              onValueChange={(value) => onChange({ knowledge_base_id: value, file_ids: [] })}
            >
              <SelectTrigger aria-label="知识库">
                <SelectValue placeholder="选择本人的知识库" />
              </SelectTrigger>
              <SelectContent>
                {bases.data?.data.map((base) => (
                  <SelectItem key={base.id} value={base.id}>
                    {base.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ) : (
          <p className="self-end py-2 text-xs leading-6 text-muted-foreground">
            本次使用模型通用知识，不引用你的资料。
          </p>
        )}
      </div>
      {config.source_mode === "materials" && config.knowledge_base_id ? (
        <div className="space-y-2">
          <p className="text-xs font-semibold">文件范围（不选文件时使用知识库内有效资料）</p>
          {files.isPending ? (
            <p role="status" className="text-xs">
              正在读取文件…
            </p>
          ) : null}
          {files.data?.data.map((file) => (
            <label key={file.id} className="flex items-center gap-2 text-xs">
              <Checkbox
                disabled={disabled || fixed}
                checked={(config.file_ids ?? []).includes(file.id)}
                onCheckedChange={(checked) =>
                  onChange({
                    file_ids: checked
                      ? [...(config.file_ids ?? []), file.id]
                      : (config.file_ids ?? []).filter((id) => id !== file.id),
                  })
                }
              />
              {file.display_name}
            </label>
          ))}
          {files.data?.data.length === 0 ? (
            <p className="text-xs text-muted-foreground">知识库暂无文件，请先添加有效资料。</p>
          ) : null}
        </div>
      ) : null}
      {fixed ? (
        <p className="text-xs text-muted-foreground">
          来源范围来自所选难点，改变范围请新建直接精讲或手动难点。
        </p>
      ) : null}
      {bases.error || files.error ? (
        <p role="alert" className="text-sm text-danger">
          {bases.error?.message ?? files.error?.message}
        </p>
      ) : null}
    </fieldset>
  );
}
