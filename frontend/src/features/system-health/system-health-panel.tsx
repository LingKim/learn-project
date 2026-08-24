"use client";

import { useQuery } from "@tanstack/react-query";
import { Database, HardDrive, RefreshCw, Server } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { DependencyCheck, ReadyResponse } from "@/lib/api/generated/types.gen";

import { getSystemHealth, systemHealthQueryKey } from "./api";

const services = [
  { key: "postgresql", label: "PostgreSQL", detail: "业务数据", icon: Database },
  { key: "redis", label: "Redis", detail: "缓存与任务基础", icon: Server },
  { key: "rustfs", label: "RustFS", detail: "对象存储", icon: HardDrive },
] as const;

function statusLabel(check: DependencyCheck | undefined) {
  if (!check) return "等待检查";
  return check.status === "up" ? "可用" : "不可用";
}

function lastUpdatedText(updatedAt: number) {
  if (!updatedAt) return "尚未完成检查";
  return `更新于 ${new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(updatedAt)}`;
}

export function SystemHealthPanel() {
  const query = useQuery<ReadyResponse>({
    queryKey: systemHealthQueryKey,
    queryFn: getSystemHealth,
    refetchInterval: 30_000,
    retry: false,
  });

  const isReady = query.data?.status === "ready";

  return (
    <div className="w-full" aria-live="polite">
      <div className="flex items-start justify-between gap-6">
        <div>
          <p className="text-xs font-semibold tracking-[0.16em] text-muted-foreground uppercase">
            Readiness
          </p>
          <h2 className="mt-3 text-2xl font-semibold tracking-[-0.035em] text-foreground">
            基础服务
          </h2>
        </div>
        {query.isPending ? (
          <Badge variant="outline">检查中</Badge>
        ) : query.isError ? (
          <Badge variant="danger">API 未连接</Badge>
        ) : isReady ? (
          <Badge variant="success">全部就绪</Badge>
        ) : (
          <Badge variant="danger">存在异常</Badge>
        )}
      </div>

      <div className="mt-8 border-y border-border">
        {services.map(({ key, label, detail, icon: Icon }) => {
          const check = query.data?.checks[key];
          const isUp = check?.status === "up";
          return (
            <div
              key={key}
              className="grid min-h-20 grid-cols-[auto_1fr_auto] items-center gap-4 border-b border-border py-4 last:border-b-0"
            >
              <span className="grid size-10 place-items-center rounded-md border border-border bg-surface text-foreground">
                <Icon aria-hidden="true" className="size-[1.125rem]" strokeWidth={1.8} />
              </span>
              <div className="min-w-0">
                <p className="font-medium text-foreground">{label}</p>
                <p className="mt-0.5 truncate text-sm text-muted-foreground">{detail}</p>
              </div>
              <span className="inline-flex items-center gap-2 text-sm font-medium text-foreground">
                <span
                  className={
                    query.isPending
                      ? "size-2 rounded-full bg-muted-foreground motion-safe:animate-pulse"
                      : isUp
                        ? "size-2 rounded-full bg-success"
                        : "size-2 rounded-full bg-danger"
                  }
                />
                {query.isPending ? "检查中" : statusLabel(check)}
              </span>
            </div>
          );
        })}
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
        <p className="text-sm text-muted-foreground">
          {query.isError ? "无法访问后端健康接口" : lastUpdatedText(query.dataUpdatedAt)}
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          <RefreshCw aria-hidden="true" className={query.isFetching ? "animate-spin" : undefined} />
          重新检查
        </Button>
      </div>

      <p className="mt-8 border-l-2 border-primary pl-4 text-sm leading-6 text-muted-foreground">
        健康状态只包含脱敏运行信息，不展示连接串、凭据或任何用户业务内容。
      </p>
    </div>
  );
}
