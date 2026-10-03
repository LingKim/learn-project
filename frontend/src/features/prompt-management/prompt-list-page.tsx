"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
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
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { DefinitionFilters, DefinitionView } from "./api";
import { promptDefinitionsOptions, promptVersionsOptions } from "./queries";
import { dateText, PromptError } from "./display";

function DefinitionRow({ definition }: { definition: DefinitionView }) {
  const timeline = useQuery(promptVersionsOptions(definition.id));
  const active = timeline.data?.data.find((version) => version.id === definition.active_version_id);
  return (
    <TableRow>
      <TableCell>
        <Link
          className="font-semibold underline underline-offset-4"
          href={`/admin/prompts/${definition.id}`}
          prefetch={false}
        >
          {definition.display_name}
        </Link>
        <p className="mt-1 text-xs text-muted-foreground">
          {definition.agent_key} / {definition.scene_key}
        </p>
      </TableCell>
      <TableCell>
        {{ shared: "公共规则", agent: "Agent规则", task: "任务场景" }[definition.template_kind]}
      </TableCell>
      <TableCell>
        <Badge variant={definition.runtime_status === "enabled" ? "success" : "outline"}>
          {definition.runtime_status === "enabled" ? "已启用" : "已停用"}
        </Badge>
      </TableCell>
      <TableCell>
        {active
          ? `v${active.version}`
          : definition.active_version_id
            ? definition.active_version_id.slice(0, 8)
            : "未发布"}
      </TableCell>
      <TableCell>{dateText(active?.published_at)}</TableCell>
      <TableCell>
        {active?.latest_evaluation ? (
          <Badge variant={active.latest_evaluation.passed ? "success" : "danger"}>
            {active.latest_evaluation.passed ? "评测通过" : "评测未通过"}
          </Badge>
        ) : (
          "—"
        )}
      </TableCell>
      <TableCell>
        <Button asChild variant="outline" size="sm">
          <Link href={`/admin/prompts/${definition.id}`} prefetch={false}>
            版本详情
          </Link>
        </Button>
      </TableCell>
    </TableRow>
  );
}

export function PromptListPage() {
  const [agent, setAgent] = useState("");
  const [scene, setScene] = useState("");
  const [kind, setKind] = useState("all");
  const [status, setStatus] = useState("all");
  const [filters, setFilters] = useState<DefinitionFilters>({ page: 1 });
  const query = useQuery(promptDefinitionsOptions(filters));
  function filter(event: FormEvent) {
    event.preventDefault();
    setFilters({
      page: 1,
      agent_key: agent.trim() || undefined,
      scene_key: scene.trim() || undefined,
      template_kind: kind === "all" ? undefined : kind,
      runtime_status: status === "all" ? undefined : status,
    });
  }
  return (
    <section className="mx-auto max-w-[1440px] px-4 py-8 sm:px-8 xl:px-12">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">提示词管理</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            管理真实注册场景的不可变版本、合成评测与发布。
          </p>
        </div>
        <Button variant="outline" disabled={query.isFetching} onClick={() => void query.refetch()}>
          刷新
        </Button>
      </div>
      <form
        onSubmit={filter}
        className="mt-7 grid gap-4 border-y border-border py-5 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_180px_180px_auto]"
      >
        <div className="grid gap-2">
          <Label htmlFor="prompt-agent">Agent</Label>
          <Input
            id="prompt-agent"
            value={agent}
            onChange={(event) => setAgent(event.target.value)}
            placeholder="按 Agent 筛选"
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="prompt-scene">场景</Label>
          <Input
            id="prompt-scene"
            value={scene}
            onChange={(event) => setScene(event.target.value)}
            placeholder="按场景筛选"
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="prompt-kind">模板类型</Label>
          <Select value={kind} onValueChange={setKind}>
            <SelectTrigger id="prompt-kind">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部类型</SelectItem>
              <SelectItem value="shared">公共规则</SelectItem>
              <SelectItem value="agent">Agent规则</SelectItem>
              <SelectItem value="task">任务场景</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-2">
          <Label htmlFor="prompt-status">运行状态</Label>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger id="prompt-status">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部状态</SelectItem>
              <SelectItem value="enabled">已启用</SelectItem>
              <SelectItem value="disabled">已停用</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Button className="self-end" type="submit">
          筛选
        </Button>
      </form>
      <div className="mt-6" aria-live="polite">
        {query.isPending ? (
          <p className="py-12 text-sm text-muted-foreground">正在加载提示词定义…</p>
        ) : query.isError ? (
          <PromptError error={query.error} />
        ) : query.data.data.length === 0 ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            没有符合条件的已注册提示词定义。
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>模板 / 场景</TableHead>
                <TableHead>类型</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>活动版本</TableHead>
                <TableHead>发布时间</TableHead>
                <TableHead>活动版本评测</TableHead>
                <TableHead>操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.data.data.map((item) => (
                <DefinitionRow key={item.id} definition={item} />
              ))}
            </TableBody>
          </Table>
        )}
      </div>
      {query.data && (
        <div className="mt-6 flex items-center justify-between gap-3 text-sm text-muted-foreground">
          <span>
            共 {query.data.meta.total} 个定义 · 第 {query.data.meta.page} 页
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={query.data.meta.page <= 1 || query.isFetching}
              onClick={() => setFilters({ ...filters, page: query.data!.meta.page - 1 })}
            >
              上一页
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={query.data.meta.page >= query.data.meta.total_pages || query.isFetching}
              onClick={() => setFilters({ ...filters, page: query.data!.meta.page + 1 })}
            >
              下一页
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
