"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Download,
  FileText,
  FolderInput,
  Pencil,
  Search,
  Trash2,
  Upload,
} from "lucide-react";
import Link from "next/link";
import { useDeferredValue, useRef, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/badge";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { toApiError } from "@/lib/api/errors";

import { AIProcessingNotice, DocumentProcessingStatus } from "./processing-status";

import type { KnowledgeFileView } from "./api";
import { ContentShell } from "./content-shell";
import { DeleteImpactDialog } from "./delete-impact-dialog";
import {
  deleteKnowledgeFileMutationOptions,
  downloadKnowledgeFileMutationOptions,
  knowledgeBaseListQueryOptions,
  knowledgeFileListQueryOptions,
  moveKnowledgeFileMutationOptions,
  updateKnowledgeFileMutationOptions,
  uploadKnowledgeFileMutationOptions,
} from "./queries";

type FileDialogState = { mode: "rename" | "move"; file: KnowledgeFileView } | null;

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function fileStatus(file: KnowledgeFileView) {
  const labels: Record<string, string> = {
    pending_processing: "已上传·待解析",
    processing: "解析中",
    succeeded: "已完成",
    failed: "处理失败",
    cancelled: "已取消",
  };
  return labels[file.processing_status] ?? file.processing_status;
}

function statusVariant(file: KnowledgeFileView): "warm" | "success" | "danger" | "outline" {
  if (file.processing_status === "succeeded") return "success";
  if (file.processing_status === "failed") return "danger";
  if (file.processing_status === "pending_processing" || file.processing_status === "processing")
    return "warm";
  return "outline";
}

export function KnowledgeBaseDetail({ knowledgeBaseId }: { knowledgeBaseId: string }) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search.trim());
  const [status, setStatus] = useState("all");
  const [fileDialog, setFileDialog] = useState<FileDialogState>(null);
  const [dialogValue, setDialogValue] = useState("");
  const [localError, setLocalError] = useState("");
  const [deleteFile, setDeleteFile] = useState<KnowledgeFileView | null>(null);
  const [deleteMode, setDeleteMode] = useState<"SOURCE_ONLY" | "CASCADE">("SOURCE_ONLY");

  const basesQuery = useQuery(knowledgeBaseListQueryOptions(1, 100));
  const filesQuery = useQuery(
    knowledgeFileListQueryOptions(
      knowledgeBaseId,
      page,
      20,
      deferredSearch,
      status === "all" ? "" : status,
    ),
  );
  const uploadMutation = useMutation(uploadKnowledgeFileMutationOptions(queryClient));
  const updateMutation = useMutation(updateKnowledgeFileMutationOptions(queryClient));
  const moveMutation = useMutation(moveKnowledgeFileMutationOptions(queryClient));
  const deleteMutation = useMutation(deleteKnowledgeFileMutationOptions(queryClient));
  const downloadMutation = useMutation(downloadKnowledgeFileMutationOptions());
  const currentBase = basesQuery.data?.data.find((item) => item.id === knowledgeBaseId);
  const targetBases = basesQuery.data?.data.filter((item) => item.id !== knowledgeBaseId) ?? [];

  function openFileDialog(mode: "rename" | "move", file: KnowledgeFileView) {
    setFileDialog({ mode, file });
    setDialogValue(mode === "rename" ? file.display_name : (targetBases[0]?.id ?? ""));
    setLocalError("");
  }

  async function submitFileDialog(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!fileDialog || !dialogValue.trim()) {
      setLocalError(fileDialog?.mode === "move" ? "请选择目标知识库" : "请输入文件名");
      return;
    }
    try {
      if (fileDialog.mode === "rename") {
        await updateMutation.mutateAsync({
          knowledgeBaseId,
          knowledgeFileId: fileDialog.file.id,
          body: { display_name: dialogValue.trim() },
        });
      } else {
        await moveMutation.mutateAsync({
          knowledgeBaseId,
          knowledgeFileId: fileDialog.file.id,
          body: { target_knowledge_base_id: dialogValue },
        });
      }
      setFileDialog(null);
    } catch (error) {
      setLocalError(toApiError(error).message);
    }
  }

  async function handleUpload(file: File | undefined) {
    if (!file) return;
    try {
      await uploadMutation.mutateAsync({ knowledgeBaseId, file });
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleDownload(file: KnowledgeFileView) {
    const target = window.open("about:blank", "_blank");
    if (target) target.opener = null;
    try {
      const result = await downloadMutation.mutateAsync({
        knowledgeBaseId,
        knowledgeFileId: file.id,
      });
      if (target) target.location.href = result.url;
      else window.location.assign(result.url);
    } catch (error) {
      target?.close();
      throw error;
    }
  }

  return (
    <ContentShell>
      <section className="mx-auto w-full max-w-[90rem] px-4 py-8 sm:px-8 sm:py-10">
        <Link
          href="/content"
          className="inline-flex min-h-10 items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
        >
          <ArrowLeft className="size-4" />
          返回知识库
        </Link>
        <AIProcessingNotice />
        <div className="mt-4 flex flex-col gap-5 border-b border-border pb-7 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-semibold tracking-[0.18em] text-accent-foreground uppercase">
              Knowledge Base
            </p>
            <h1 className="mt-2 text-3xl font-bold tracking-[-0.04em]">
              {currentBase?.name ?? (basesQuery.isPending ? "正在加载…" : "知识库详情")}
            </h1>
            <p className="mt-2 text-sm text-muted-foreground">
              支持 PDF、DOCX、TXT、MD；校验通过后自动解析并建立检索索引；扫描 PDF 按页识别文字。
            </p>
          </div>
          <div>
            <input
              ref={fileInputRef}
              className="sr-only"
              id="knowledge-file-upload"
              type="file"
              accept=".pdf,.docx,.txt,.md"
              onChange={(event) => void handleUpload(event.target.files?.[0])}
            />
            <Button
              variant="brand"
              disabled={uploadMutation.isPending}
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload />
              {uploadMutation.isPending ? "正在上传与校验" : "上传资料"}
            </Button>
          </div>
        </div>

        {uploadMutation.isError ? (
          <p
            role="alert"
            className="mt-4 rounded-md bg-[color-mix(in_oklch,var(--danger)_10%,var(--surface))] px-4 py-3 text-sm text-danger"
          >
            {uploadMutation.error.message}
          </p>
        ) : null}

        <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              aria-label="搜索文件"
              className="h-10 bg-surface pl-9"
              placeholder="搜索文件名"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
            />
          </div>
          <Select
            value={status}
            onValueChange={(value) => {
              setStatus(value);
              setPage(1);
            }}
          >
            <SelectTrigger className="w-full sm:w-48" aria-label="文件状态">
              <SelectValue placeholder="全部状态" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部状态</SelectItem>
              <SelectItem value="pending_processing">已上传·待解析</SelectItem>
              <SelectItem value="processing">解析中</SelectItem>
              <SelectItem value="succeeded">已完成</SelectItem>
              <SelectItem value="failed">处理失败</SelectItem>
              <SelectItem value="cancelled">已取消</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="mt-4 overflow-hidden border border-border bg-surface">
          {filesQuery.isPending ? (
            <div className="py-20 text-center text-sm text-muted-foreground" aria-busy="true">
              正在加载文件…
            </div>
          ) : filesQuery.isError ? (
            <div role="alert" className="py-16 text-center">
              <p className="text-sm text-danger">{filesQuery.error.message}</p>
              <Button className="mt-4" variant="outline" onClick={() => filesQuery.refetch()}>
                重新加载
              </Button>
            </div>
          ) : filesQuery.data.data.length === 0 ? (
            <div className="py-20 text-center">
              <FileText className="mx-auto size-9 text-muted-foreground" />
              <p className="mt-4 font-semibold">
                {deferredSearch || status !== "all" ? "没有匹配的文件" : "知识库还是空的"}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                {deferredSearch || status !== "all"
                  ? "调整搜索或筛选条件后再试。"
                  : "上传第一份资料，开始积累可检索的内容。"}
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader className="bg-muted/75">
                <TableRow>
                  <TableHead className="min-w-64">文件名</TableHead>
                  <TableHead>大小</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>更新时间</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filesQuery.data.data.map((file) => (
                  <TableRow key={file.id}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <span className="grid size-9 shrink-0 place-items-center rounded-md bg-muted">
                          <FileText className="size-4 text-accent-foreground" />
                        </span>
                        <div className="min-w-0">
                          <p className="max-w-md truncate font-semibold">{file.display_name}</p>
                          <p className="mt-0.5 text-xs text-muted-foreground">
                            {file.detected_mime}
                          </p>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {formatBytes(file.byte_size)}
                    </TableCell>
                    <TableCell>
                      <Badge variant={statusVariant(file)}>{fileStatus(file)}</Badge>
                      <DocumentProcessingStatus knowledgeBaseId={knowledgeBaseId} file={file} />
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {formatDate(file.updated_at)}
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          aria-label={`重命名 ${file.display_name}`}
                          onClick={() => openFileDialog("rename", file)}
                        >
                          <Pencil />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          aria-label={`移动 ${file.display_name}`}
                          disabled={targetBases.length === 0}
                          onClick={() => openFileDialog("move", file)}
                        >
                          <FolderInput />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          aria-label={`下载 ${file.display_name}`}
                          disabled={
                            downloadMutation.isPending || file.validation_status !== "available"
                          }
                          onClick={() => void handleDownload(file)}
                        >
                          <Download />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          aria-label={`删除 ${file.display_name}`}
                          onClick={() => {
                            setDeleteFile(file);
                            setDeleteMode("SOURCE_ONLY");
                          }}
                        >
                          <Trash2 />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>

        {(filesQuery.data?.meta.total_pages ?? 0) > 1 ? (
          <div className="mt-5 flex items-center justify-end gap-3">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((value) => value - 1)}
            >
              上一页
            </Button>
            <span className="text-xs text-muted-foreground">
              第 {page} / {filesQuery.data?.meta.total_pages} 页
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= (filesQuery.data?.meta.total_pages ?? 1)}
              onClick={() => setPage((value) => value + 1)}
            >
              下一页
            </Button>
          </div>
        ) : null}
      </section>

      <Dialog open={Boolean(fileDialog)} onOpenChange={(open) => !open && setFileDialog(null)}>
        <DialogContent>
          <form className="grid gap-5" onSubmit={submitFileDialog}>
            <DialogHeader>
              <DialogTitle>{fileDialog?.mode === "move" ? "移动文件" : "重命名文件"}</DialogTitle>
              <DialogDescription>
                {fileDialog?.mode === "move"
                  ? "移动后文件将从当前知识库消失，并出现在目标知识库。"
                  : "只能修改文件名，不能改变原扩展名。"}
              </DialogDescription>
            </DialogHeader>
            {fileDialog?.mode === "move" ? (
              <div className="grid gap-2">
                <Label>目标知识库</Label>
                <Select value={dialogValue} onValueChange={setDialogValue}>
                  <SelectTrigger aria-label="目标知识库">
                    <SelectValue placeholder="请选择" />
                  </SelectTrigger>
                  <SelectContent>
                    {targetBases.map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : (
              <div className="grid gap-2">
                <Label htmlFor="knowledge-file-name">文件名</Label>
                <Input
                  id="knowledge-file-name"
                  autoFocus
                  maxLength={255}
                  value={dialogValue}
                  onChange={(event) => setDialogValue(event.target.value)}
                />
              </div>
            )}
            {localError ? (
              <p role="alert" className="text-xs text-danger">
                {localError}
              </p>
            ) : null}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setFileDialog(null)}>
                取消
              </Button>
              <Button
                type="submit"
                variant="brand"
                disabled={updateMutation.isPending || moveMutation.isPending}
              >
                {updateMutation.isPending || moveMutation.isPending ? "正在保存" : "确认"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <DeleteImpactDialog
        kind="file"
        open={Boolean(deleteFile)}
        name={deleteFile?.display_name ?? ""}
        knowledgeBaseId={knowledgeBaseId}
        knowledgeFileId={deleteFile?.id}
        mode={deleteMode}
        pending={deleteMutation.isPending}
        onModeChange={setDeleteMode}
        onOpenChange={(open) => !open && setDeleteFile(null)}
        onConfirm={(confirmationToken) => {
          if (!deleteFile) return;
          deleteMutation.mutate(
            {
              knowledgeBaseId,
              knowledgeFileId: deleteFile.id,
              body: { confirmation_token: confirmationToken, mode: deleteMode },
            },
            { onSuccess: () => setDeleteFile(null) },
          );
        }}
      />
    </ContentShell>
  );
}
