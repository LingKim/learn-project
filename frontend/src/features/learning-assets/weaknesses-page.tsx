"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { userProfileKeys } from "@/features/user-profile/queries";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { WeaknessCreate, WeaknessPatch, WeaknessView, WeaknessFilters } from "./api";
import { AssetEmpty, AssetLayout, masteryLabels, severityLabels } from "./asset-layout";
import { WeaknessForm } from "./weakness-form";
import { createWeaknessOptions, learningAssetKeys, weaknessListOptions } from "./queries";

export function WeaknessesPage() {
  const router = useRouter();
  const client = useQueryClient();
  const [filters, setFilters] = useState<WeaknessFilters>({ decision: "confirmed", page: 1 });
  const [createOpen, setCreateOpen] = useState(false);
  const keys = useRef(new Map<string, string>());
  const list = useQuery(weaknessListOptions(filters));
  const create = useMutation(createWeaknessOptions());
  function filter(patch: Partial<WeaknessFilters>) {
    setFilters((old) => ({ ...old, ...patch, page: patch.page ?? 1 }));
  }
  async function save(body: Omit<WeaknessCreate, "request_key"> | WeaknessPatch) {
    if ("expected_version" in body) return;
    const signature = JSON.stringify(body);
    let requestKey = keys.current.get(signature);
    if (!requestKey) {
      requestKey = crypto.randomUUID();
      keys.current.set(signature, requestKey);
    }
    const result = await create.mutateAsync({ ...body, request_key: requestKey });
    await Promise.all([
      client.invalidateQueries({ queryKey: learningAssetKeys.all }),
      client.invalidateQueries({ queryKey: userProfileKeys.detail() }),
    ]);
    router.push(`/weaknesses/${result.data.id}`);
  }
  return (
    <AssetLayout>
      <div className="space-y-[14px]">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold">难点资产库</h1>
            <p className="mt-1 text-xs text-muted-foreground">
              {list.data
                ? `共 ${list.data.meta.total} 个${decisionLabels[filters.decision ?? "confirmed"]}`
                : "查看本人的难点与学习证据"}
            </p>
          </div>
          <Button
            variant="brand"
            onClick={() => {
              create.reset();
              setCreateOpen(true);
            }}
          >
            <Plus aria-hidden="true" className="size-4" />
            手动创建难点
          </Button>
        </header>
        <div className="flex flex-wrap gap-3">
          {(
            [
              ["confirmed", "正式资产"],
              ["pending", "待确认候选"],
              ["ignored", "已忽略候选"],
              ["revoked", "已撤销资产"],
            ] as const
          ).map(([value, label]) => (
            <Button
              key={value}
              variant={filters.decision === value ? "brand" : "outline"}
              aria-pressed={filters.decision === value}
              onClick={() => filter({ decision: value })}
            >
              {label}
            </Button>
          ))}
        </div>
        <div className="grid min-w-0 gap-2 sm:grid-cols-2 xl:grid-cols-6">
          <Input
            aria-label="搜索难点"
            placeholder="搜索难点名称"
            value={filters.query ?? ""}
            onChange={(e) => filter({ query: e.target.value })}
          />
          <Input
            aria-label="筛选领域"
            placeholder="领域"
            value={filters.domain ?? ""}
            onChange={(e) => filter({ domain: e.target.value })}
          />
          <Input
            aria-label="筛选标签"
            placeholder="标签"
            value={filters.tags?.[0] ?? ""}
            onChange={(e) =>
              filter({ tags: e.target.value.trim() ? [e.target.value.trim()] : undefined })
            }
          />
          <Select
            value={filters.severity ?? "all"}
            onValueChange={(value) =>
              filter({
                severity: value === "all" ? undefined : (value as WeaknessView["severity"]),
              })
            }
          >
            <SelectTrigger aria-label="筛选严重度">
              <SelectValue placeholder="严重度" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">严重度：全部</SelectItem>
              {Object.entries(severityLabels).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={filters.mastery_state ?? "all"}
            onValueChange={(value) =>
              filter({
                mastery_state:
                  value === "all" ? undefined : (value as WeaknessView["mastery_state"]),
              })
            }
          >
            <SelectTrigger aria-label="筛选掌握状态">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">掌握状态：全部</SelectItem>
              {Object.entries(masteryLabels).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={filters.source_mode ?? "all"}
            onValueChange={(value) =>
              filter({
                source_mode: value === "all" ? undefined : (value as WeaknessView["source_mode"]),
              })
            }
          >
            <SelectTrigger aria-label="筛选来源模式">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">来源模式：全部</SelectItem>
              <SelectItem value="general">通用模式</SelectItem>
              <SelectItem value="materials">资料模式</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {list.isPending ? (
          <p role="status" className="py-8 text-sm">
            正在读取难点…
          </p>
        ) : list.error ? (
          <div className="space-y-3 py-8">
            <p role="alert" className="text-sm text-danger">
              {list.error.message}
            </p>
            <Button
              variant="outline"
              onClick={() => {
                void list.refetch();
              }}
            >
              重新读取
            </Button>
          </div>
        ) : list.data?.data.length ? (
          <ul className="divide-y divide-border border-y border-border">
            {list.data.data.map((item) => (
              <li
                key={item.id}
                className="flex min-w-0 flex-wrap items-center gap-3 px-3 py-[14px]"
              >
                <Link href={`/weaknesses/${item.id}`} className="min-w-0 flex-1 hover:underline">
                  <h2 className="break-words text-sm font-semibold">{item.title}</h2>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {[item.domain, ...item.tags].filter(Boolean).join(" / ") || "未设置领域和标签"}
                  </p>
                </Link>
                <Badge variant="outline">严重度{severityLabels[item.severity]}</Badge>
                <Badge variant={item.mastery_state === "mastered" ? "success" : "warm"}>
                  {item.decision === "confirmed"
                    ? masteryLabels[item.mastery_state]
                    : decisionLabels[item.decision]}
                </Badge>
                <span className="text-xs text-muted-foreground">
                  {item.source_mode === "materials" ? "资料模式" : "通用模式"} · 证据{" "}
                  {item.available_evidence_count} / {item.evidence_count} ·{" "}
                  {item.source_available
                    ? item.evidence_sufficient
                      ? "证据充分"
                      : "证据待核验"
                    : "来源不可用"}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <AssetEmpty title={`暂无符合条件的${decisionLabels[filters.decision ?? "confirmed"]}`}>
            可以手动创建难点，或完成练习后查看相关证据。
          </AssetEmpty>
        )}
        {list.data && list.data.meta.total_pages > 1 ? (
          <nav aria-label="难点分页" className="flex items-center justify-end gap-3">
            <Button
              variant="outline"
              size="sm"
              disabled={(filters.page ?? 1) <= 1}
              onClick={() => filter({ page: (filters.page ?? 1) - 1 })}
            >
              上一页
            </Button>
            <span className="text-xs">
              {filters.page ?? 1} / {list.data.meta.total_pages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={(filters.page ?? 1) >= list.data.meta.total_pages}
              onClick={() => filter({ page: (filters.page ?? 1) + 1 })}
            >
              下一页
            </Button>
          </nav>
        ) : null}
      </div>
      <Dialog
        open={createOpen}
        onOpenChange={(open) => {
          if (!create.isPending) setCreateOpen(open);
        }}
      >
        <DialogContent className="max-h-[90dvh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>手动创建难点</DialogTitle>
            <DialogDescription>明确知识点和来源范围，保存后首次生成文字卡片。</DialogDescription>
          </DialogHeader>
          <WeaknessForm
            pending={create.isPending}
            error={create.error?.message}
            onCancel={() => setCreateOpen(false)}
            onSubmit={(body) => {
              void save(body).catch(() => {});
            }}
          />
        </DialogContent>
      </Dialog>
    </AssetLayout>
  );
}
const decisionLabels = {
  confirmed: "正式资产",
  pending: "待确认候选",
  ignored: "已忽略候选",
  revoked: "已撤销资产",
};
