"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Folder, FolderOpen, FolderPlus, Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toApiError } from "@/lib/api/errors";

import type { KnowledgeBaseView } from "./api";
import { ContentShell } from "./content-shell";
import { DeleteImpactDialog } from "./delete-impact-dialog";
import {
  createKnowledgeBaseMutationOptions,
  deleteKnowledgeBaseMutationOptions,
  knowledgeBaseListQueryOptions,
  updateKnowledgeBaseMutationOptions,
} from "./queries";

type NameDialogState = { mode: "create" | "rename"; item?: KnowledgeBaseView } | null;

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function KnowledgeBaseOverview() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [nameDialog, setNameDialog] = useState<NameDialogState>(null);
  const [name, setName] = useState("");
  const [localError, setLocalError] = useState("");
  const [deleteItem, setDeleteItem] = useState<KnowledgeBaseView | null>(null);
  const [deleteMode, setDeleteMode] = useState<"SOURCE_ONLY" | "CASCADE">("SOURCE_ONLY");
  const listQuery = useQuery(knowledgeBaseListQueryOptions(page, 20));
  const createMutation = useMutation(createKnowledgeBaseMutationOptions(queryClient));
  const updateMutation = useMutation(updateKnowledgeBaseMutationOptions(queryClient));
  const deleteMutation = useMutation(deleteKnowledgeBaseMutationOptions(queryClient));

  function openNameDialog(state: NonNullable<NameDialogState>) {
    setNameDialog(state);
    setName(state.item?.name ?? "");
    setLocalError("");
  }

  async function submitName(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = name.trim();
    if (!normalized) {
      setLocalError("请输入知识库名称");
      return;
    }
    try {
      if (nameDialog?.mode === "rename" && nameDialog.item) {
        await updateMutation.mutateAsync({ id: nameDialog.item.id, body: { name: normalized } });
      } else {
        await createMutation.mutateAsync({ name: normalized });
      }
      setNameDialog(null);
    } catch (error) {
      setLocalError(toApiError(error).message);
    }
  }

  return (
    <ContentShell>
      <section className="mx-auto w-full max-w-[90rem] px-4 py-8 sm:px-8 sm:py-10">
        <div className="flex flex-col gap-5 border-b border-border pb-7 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-semibold tracking-[0.18em] text-accent-foreground uppercase">
              Content Library
            </p>
            <h1 className="mt-2 text-3xl font-bold tracking-[-0.04em]">内容库 / 知识库</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              每位用户始终至少保留一个知识库。资料上传后先进入“已上传·待解析”，不会伪装成已解析可用。
            </p>
          </div>
          <Button variant="brand" onClick={() => openNameDialog({ mode: "create" })}>
            <FolderPlus />
            创建知识库
          </Button>
        </div>

        <div className="grid gap-3 border-b border-border py-5 sm:grid-cols-3">
          <div className="py-2 sm:border-r sm:border-border sm:px-4 first:pl-0">
            <p className="text-xs text-muted-foreground">知识库</p>
            <p className="mt-1 text-2xl font-bold">{listQuery.data?.meta.total ?? "—"} 个</p>
          </div>
          <div className="py-2 sm:border-r sm:border-border sm:px-4">
            <p className="text-xs text-muted-foreground">当前页</p>
            <p className="mt-1 text-2xl font-bold">{listQuery.data?.data.length ?? "—"} 个</p>
          </div>
          <div className="py-2 sm:px-4">
            <p className="text-xs text-muted-foreground">保留规则</p>
            <p className="mt-1 text-base font-bold">至少 1 个有效知识库</p>
          </div>
        </div>

        <div className="mt-7 flex items-center justify-between">
          <h2 className="text-base font-bold">我的知识库</h2>
          {listQuery.isFetching ? (
            <span className="text-xs text-muted-foreground">正在刷新…</span>
          ) : null}
        </div>

        {listQuery.isPending ? (
          <div
            className="mt-4 border-y border-border py-16 text-center text-sm text-muted-foreground"
            aria-busy="true"
          >
            正在加载知识库…
          </div>
        ) : listQuery.isError ? (
          <div role="alert" className="mt-4 border-y border-border py-12 text-center">
            <p className="text-sm text-danger">{listQuery.error.message}</p>
            <Button className="mt-4" variant="outline" onClick={() => listQuery.refetch()}>
              重新加载
            </Button>
          </div>
        ) : listQuery.data.data.length === 0 ? (
          <div className="mt-4 border-y border-border py-16 text-center">
            <Folder className="mx-auto size-8 text-muted-foreground" />
            <p className="mt-4 font-semibold">还没有知识库</p>
            <p className="mt-1 text-sm text-muted-foreground">创建一个知识库后即可上传学习资料。</p>
          </div>
        ) : (
          <ul className="mt-4 border-t border-border">
            {listQuery.data.data.map((item) => (
              <li
                key={item.id}
                className="group flex flex-col gap-4 border-b border-border px-3 py-4 transition-colors hover:bg-muted/35 sm:flex-row sm:items-center"
              >
                <Link
                  href={`/content/${item.id}`}
                  className="flex min-w-0 flex-1 items-center gap-4 focus-visible:outline-2 focus-visible:outline-ring"
                >
                  <span
                    className={`grid size-10 shrink-0 place-items-center rounded-md ${item.is_default ? "bg-primary/35" : "bg-muted"}`}
                  >
                    {item.is_default ? (
                      <FolderOpen className="size-5 text-accent-foreground" />
                    ) : (
                      <Folder className="size-5 text-accent-foreground" />
                    )}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-bold">{item.name}</span>
                    <span className="mt-1 block text-xs text-muted-foreground">
                      {item.is_default ? "默认知识库 · " : ""}更新于 {formatDate(item.updated_at)}
                    </span>
                  </span>
                </Link>
                <div className="flex items-center gap-1 sm:opacity-70 sm:transition-opacity sm:group-hover:opacity-100">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    aria-label={`重命名 ${item.name}`}
                    onClick={() => openNameDialog({ mode: "rename", item })}
                  >
                    <Pencil />
                    重命名
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    aria-label={`删除 ${item.name}`}
                    onClick={() => {
                      setDeleteItem(item);
                      setDeleteMode("SOURCE_ONLY");
                    }}
                  >
                    <Trash2 />
                    删除
                  </Button>
                  <Link
                    href={`/content/${item.id}`}
                    aria-label={`进入${item.name}`}
                    className="grid size-9 place-items-center rounded-md hover:bg-muted"
                  >
                    <ChevronRight className="size-4" />
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        )}

        {(listQuery.data?.meta.total_pages ?? 0) > 1 ? (
          <div className="mt-6 flex items-center justify-end gap-3">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((value) => value - 1)}
            >
              上一页
            </Button>
            <span className="text-xs text-muted-foreground">
              第 {page} / {listQuery.data?.meta.total_pages} 页
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= (listQuery.data?.meta.total_pages ?? 1)}
              onClick={() => setPage((value) => value + 1)}
            >
              下一页
            </Button>
          </div>
        ) : null}
      </section>

      <Dialog open={Boolean(nameDialog)} onOpenChange={(open) => !open && setNameDialog(null)}>
        <DialogContent>
          <form onSubmit={submitName} className="grid gap-5">
            <DialogHeader>
              <DialogTitle>
                {nameDialog?.mode === "rename" ? "重命名知识库" : "创建知识库"}
              </DialogTitle>
              <DialogDescription>名称用于区分资料范围，最长 100 个字符。</DialogDescription>
            </DialogHeader>
            <div className="grid gap-2">
              <Label htmlFor="knowledge-base-name">知识库名称</Label>
              <Input
                id="knowledge-base-name"
                autoFocus
                maxLength={100}
                value={name}
                onChange={(event) => setName(event.target.value)}
                aria-invalid={Boolean(localError)}
              />
              {localError ? (
                <p role="alert" className="text-xs text-danger">
                  {localError}
                </p>
              ) : null}
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setNameDialog(null)}>
                取消
              </Button>
              <Button
                type="submit"
                variant="brand"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                {createMutation.isPending || updateMutation.isPending ? "正在保存" : "保存"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <DeleteImpactDialog
        kind="knowledge-base"
        open={Boolean(deleteItem)}
        name={deleteItem?.name ?? ""}
        knowledgeBaseId={deleteItem?.id ?? ""}
        mode={deleteMode}
        pending={deleteMutation.isPending}
        onModeChange={setDeleteMode}
        onOpenChange={(open) => !open && setDeleteItem(null)}
        onConfirm={(confirmationToken) => {
          if (!deleteItem) return;
          deleteMutation.mutate(
            {
              id: deleteItem.id,
              body: { confirmation_token: confirmationToken, mode: deleteMode },
            },
            { onSuccess: () => setDeleteItem(null) },
          );
        }}
      />
    </ContentShell>
  );
}
