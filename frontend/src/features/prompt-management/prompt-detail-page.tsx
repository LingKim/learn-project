"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { DefinitionView } from "./api";
import { dateText, PromptError, VersionBadge } from "./display";
import {
  createPromptDraftOptions,
  promptAuditOptions,
  promptDefinitionOptions,
  promptVersionOptions,
  promptVersionsOptions,
} from "./queries";
import { VersionEditor } from "./version-editor";
import { usePromptDraftMemory } from "./draft-memory";

function DraftDialog({
  definition,
  sourceVersionId,
  onCreated,
  onClose,
}: {
  definition: DefinitionView;
  sourceVersionId: string | null;
  onCreated: (id: string) => void;
  onClose: () => void;
}) {
  const client = useQueryClient();
  const create = useMutation(createPromptDraftOptions(client, definition.id));
  const [change, setChange] = useState("");
  const [content, setContent] = useState("");
  // 对话框开始时固化基准，后台刷新不能静默把创建操作改到新活动版本。
  const [base] = useState(definition.active_version_id);
  async function submit() {
    try {
      const result = await create.mutateAsync({
        expected_active_version_id: base,
        source_version_id: sourceVersionId,
        content: sourceVersionId ? undefined : content || undefined,
        change_description: change.trim(),
      });
      onCreated(result.data.id);
      onClose();
    } catch {
      /* 共享ApiError在对话框中展示，输入保留。 */
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !create.isPending) onClose();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>创建草稿版本</DialogTitle>
          <DialogDescription>
            {sourceVersionId
              ? "从当前选择版本复制正文、变量和固定依赖，创建新的递增版本。"
              : "为已注册定义创建初始草稿；保存不会调用模型。"}
          </DialogDescription>
        </DialogHeader>
        <p className="break-all text-xs text-muted-foreground">活动基准：{base ?? "未发布"}</p>
        {!sourceVersionId && (
          <div className="grid gap-2">
            <Label htmlFor="initial-content">初始正文</Label>
            <Textarea
              id="initial-content"
              value={content}
              onChange={(event) => setContent(event.target.value)}
              maxLength={20000}
            />
          </div>
        )}
        <div className="grid gap-2">
          <Label htmlFor="draft-description">变更说明（必填）</Label>
          <Textarea
            id="draft-description"
            value={change}
            onChange={(event) => setChange(event.target.value)}
            maxLength={1000}
            disabled={create.isPending}
          />
        </div>
        {create.error && <PromptError error={create.error} />}
        <DialogFooter>
          <Button variant="outline" disabled={create.isPending} onClick={onClose}>
            取消
          </Button>
          <Button disabled={create.isPending || !change.trim()} onClick={() => void submit()}>
            {create.isPending ? "创建中…" : "创建草稿"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function PromptDetailPage({ definitionId }: { definitionId: string }) {
  const router = useRouter();
  const memory = usePromptDraftMemory();
  const [reloading, setReloading] = useState(false);
  const [page, setPage] = useState(1);
  const [auditPage, setAuditPage] = useState(1);
  const [selected, setSelected] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [editorKey, setEditorKey] = useState(0);
  const [draftOpen, setDraftOpen] = useState(false);
  const [leave, setLeave] = useState<{
    type: "version" | "reload" | "path" | "draft";
    value?: string;
  } | null>(null);
  const definition = useQuery(promptDefinitionOptions(definitionId));
  const versions = useQuery(promptVersionsOptions(definitionId, page));
  const audits = useQuery(promptAuditOptions(definitionId, auditPage));
  const versionId =
    selected ??
    memory.selected(definitionId) ??
    definition.data?.active_version_id ??
    versions.data?.data[0]?.id ??
    "";
  const version = useQuery(promptVersionOptions(versionId));

  function act(action: NonNullable<typeof leave>) {
    if (dirty) {
      setLeave(action);
      return;
    }
    navigate(action);
  }
  function navigate(action: NonNullable<typeof leave>) {
    memory.remove(versionId);
    setDirty(false);
    setLeave(null);
    if (action.type === "version") {
      setSelected(action.value!);
      setEditorKey((value) => value + 1);
    }
    if (action.type === "reload") {
      setReloading(true);
      void version
        .refetch()
        .then((result) => {
          if (result.isSuccess) setEditorKey((value) => value + 1);
        })
        .finally(() => setReloading(false));
    }
    if (action.type === "path") router.push(action.value!);
    if (action.type === "draft") {
      setEditorKey((value) => value + 1);
      setDraftOpen(true);
    }
  }
  useEffect(() => {
    if (!dirty) return;
    // 捕获管理页和共享导航中的离页链接；Prompt正文不写入URL或浏览器恢复存储。
    const follow = (event: MouseEvent) => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
        return;
      const anchor = event.target instanceof Element ? event.target.closest("a") : null;
      if (
        !anchor ||
        (anchor.target && anchor.target !== "_self") ||
        anchor.hasAttribute("download")
      )
        return;
      const target = new URL(anchor.href, window.location.href);
      if (
        target.href === window.location.href ||
        (target.protocol !== "http:" && target.protocol !== "https:")
      )
        return;
      event.preventDefault();
      event.stopPropagation();
      setLeave({
        type: "path",
        value:
          target.origin === window.location.origin
            ? `${target.pathname}${target.search}${target.hash}`
            : target.href,
      });
    };
    document.addEventListener("click", follow, true);
    return () => document.removeEventListener("click", follow, true);
  }, [dirty]);

  if (definition.isPending)
    return <p className="px-8 py-12 text-sm text-muted-foreground">正在加载提示词定义…</p>;
  if (definition.isError)
    return (
      <section className="px-8 py-8">
        <PromptError error={definition.error} />
      </section>
    );
  const item = definition.data;
  return (
    <section className="mx-auto max-w-[1440px] px-4 py-7 sm:px-8 xl:px-12">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => act({ type: "path", value: "/admin/prompts" })}
      >
        ← 提示词模板列表
      </Button>
      <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold">{item.display_name}</h1>
            <Badge variant={item.runtime_status === "enabled" ? "success" : "outline"}>
              {item.runtime_status === "enabled" ? "已启用" : "已停用"}
            </Badge>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            未保存草稿仅在当前后台会话内保留，离开后台或退出登录后清除。
          </p>
          <p className="mt-2 break-all text-sm text-muted-foreground">
            {item.agent_key} / {item.scene_key}
          </p>
        </div>
        <Button disabled={!item.registered_contract} onClick={() => act({ type: "draft" })}>
          创建草稿版本
        </Button>
      </div>
      <div className="mt-7 grid gap-7 lg:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="space-y-4 border-b border-border pb-6 lg:border-r lg:border-b-0 lg:pr-5">
          <h2 className="font-semibold">版本时间线</h2>
          {versions.isPending ? (
            <p className="text-sm text-muted-foreground">读取版本中…</p>
          ) : versions.isError ? (
            <PromptError error={versions.error} />
          ) : versions.data.data.length ? (
            <div className="space-y-2">
              {versions.data.data.map((entry) => (
                <button
                  type="button"
                  key={entry.id}
                  aria-current={entry.id === versionId ? "true" : undefined}
                  onClick={() => act({ type: "version", value: entry.id })}
                  className={`w-full rounded-md border border-border px-3 py-3 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring ${entry.id === versionId ? "bg-muted" : "bg-surface hover:bg-sidebar"}`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-semibold">v{entry.version}</span>
                    <VersionBadge status={entry.status} />
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">{dateText(entry.created_at)}</p>
                  <p className="mt-1 line-clamp-2 text-xs">{entry.change_description}</p>
                  {entry.id === item.active_version_id && (
                    <p className="mt-2 text-xs font-semibold text-success">当前活动版本</p>
                  )}
                  {entry.rollback_from_version_id && (
                    <p className="mt-2 text-xs text-muted-foreground">从历史版本复制回滚</p>
                  )}
                </button>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">尚无版本，可创建首个草稿。</p>
          )}
          {versions.data && (
            <div className="flex justify-between gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1 || versions.isFetching}
                onClick={() => setPage(page - 1)}
              >
                上一页
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= versions.data.meta.total_pages || versions.isFetching}
                onClick={() => setPage(page + 1)}
              >
                下一页
              </Button>
            </div>
          )}
        </aside>
        <div className="min-w-0">
          {!versionId ? (
            <p className="py-12 text-center text-sm text-muted-foreground">
              请选择或创建一个版本。
            </p>
          ) : version.isPending ? (
            <p className="py-12 text-sm text-muted-foreground">正在读取单版本正文…</p>
          ) : version.isError ? (
            <PromptError error={version.error} />
          ) : (
            <VersionEditor
              key={`${versionId}:${editorKey}`}
              definition={item}
              version={version.data}
              timeline={versions.data?.data ?? []}
              onDirty={setDirty}
              onReload={() => act({ type: "reload" })}
              onVersion={setSelected}
              reloading={reloading}
            />
          )}
        </div>
      </div>
      <section className="mt-10 space-y-4 border-t border-border pt-6">
        <h2 className="font-semibold">操作审计</h2>
        <p className="text-sm text-muted-foreground">
          仅记录操作者、版本、动作、结果和请求编号，不含 Prompt 或用户正文。
        </p>
        {audits.isPending ? (
          <p className="text-sm text-muted-foreground">正在读取审计…</p>
        ) : audits.isError ? (
          <PromptError error={audits.error} />
        ) : audits.data.data.length ? (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="border-b border-border text-muted-foreground">
                  <TableHead className="px-3 py-3 font-medium">时间</TableHead>
                  <TableHead className="px-3 py-3 font-medium">动作</TableHead>
                  <TableHead className="px-3 py-3 font-medium">版本 / 结果</TableHead>
                  <TableHead className="px-3 py-3 font-medium">操作者 / 请求编号</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {audits.data.data.map((event) => (
                  <TableRow key={event.id} className="border-b border-border">
                    <TableCell className="px-3 py-3">{dateText(event.created_at)}</TableCell>
                    <TableCell className="px-3 py-3">{event.action}</TableCell>
                    <TableCell className="px-3 py-3">
                      {event.version === null ? "—" : `v${event.version}`} · {event.outcome}
                    </TableCell>
                    <TableCell className="max-w-xs break-all px-3 py-3 text-xs">
                      {event.actor_user_id ?? "未认证"}
                      <br />
                      {event.request_id}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">尚无审计事件。</p>
        )}
        {audits.data && (
          <div className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
            <span>
              共 {audits.data.meta.total} 条 · 第 {auditPage} 页
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={auditPage <= 1 || audits.isFetching}
                onClick={() => setAuditPage(auditPage - 1)}
              >
                上一页
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={auditPage >= audits.data.meta.total_pages || audits.isFetching}
                onClick={() => setAuditPage(auditPage + 1)}
              >
                下一页
              </Button>
            </div>
          </div>
        )}
      </section>
      {draftOpen && (
        <DraftDialog
          definition={item}
          sourceVersionId={versionId || null}
          onCreated={setSelected}
          onClose={() => setDraftOpen(false)}
        />
      )}
      <Dialog
        open={leave !== null}
        onOpenChange={(open) => {
          if (!open) setLeave(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>离开未保存的草稿？</DialogTitle>
            <DialogDescription>
              当前编辑仅保存在页面内存中。继续后未保存的修改将丢失。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setLeave(null)}>
              继续编辑
            </Button>
            <Button
              onClick={() => {
                if (leave) navigate(leave);
              }}
            >
              放弃修改并继续
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
