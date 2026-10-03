"use client";

import { useRef, useState, type ReactNode } from "react";
import { Plus, Paperclip, X, FileText, LoaderCircle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ATTACHMENT_ACCEPT, type useDraftAttachments } from "./use-draft-attachments";

export function AttachmentComposer({
  draft,
  disabled,
  children,
  actions,
}: {
  draft: ReturnType<typeof useDraftAttachments>;
  disabled: boolean;
  children: ReactNode;
  actions: ReactNode;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const depth = useRef(0);
  return (
    <div
      className={`relative rounded-md border bg-surface p-3 ${dragging ? "border-primary bg-muted ring-2 ring-primary/30" : "border-border"}`}
      onDragEnter={(event) => {
        if (!event.dataTransfer.types.includes("Files")) return;
        event.preventDefault();
        depth.current++;
        if (!disabled) setDragging(true);
      }}
      onDragOver={(event) => {
        if (event.dataTransfer.types.includes("Files")) event.preventDefault();
      }}
      onDragLeave={() => {
        depth.current = Math.max(0, depth.current - 1);
        if (!depth.current) setDragging(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        depth.current = 0;
        setDragging(false);
        if (!disabled) draft.add(Array.from(event.dataTransfer.files));
      }}
      onPaste={(event) => {
        const images = Array.from(event.clipboardData.files).filter((file) =>
          file.type.startsWith("image/"),
        );
        if (images.length && !disabled) {
          event.preventDefault();
          draft.add(images);
        }
      }}
    >
      {dragging ? (
        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-md border-2 border-dashed border-primary bg-surface/95 text-sm font-medium">
          松开以上传图片或文档
        </div>
      ) : null}
      {draft.items.length ? (
        <ul aria-label="待发送附件" className="mb-2 flex flex-wrap gap-2">
          {draft.items.map((item) => (
            <li
              key={item.key}
              className="relative flex max-w-full items-center gap-2 rounded-md border border-border bg-background py-2 pr-10 pl-2"
            >
              {item.preview ? (
                <img
                  src={item.preview}
                  alt={item.file.name}
                  className="size-12 rounded object-cover"
                />
              ) : (
                <FileText className="size-7 shrink-0 text-muted-foreground" />
              )}
              <div className="min-w-0 max-w-44">
                <p className="truncate text-xs">{item.file.name}</p>
                {item.status === "uploading" ? (
                  <p
                    role="status"
                    className="mt-1 flex items-center gap-1 text-[11px] text-muted-foreground"
                  >
                    <LoaderCircle className="size-3 motion-safe:animate-spin" />
                    上传并解析中…
                  </p>
                ) : null}
                {item.error ? (
                  <p role="alert" className="mt-1 text-[11px] text-destructive">
                    {item.error}
                  </p>
                ) : null}
                {item.status === "error" ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={disabled}
                    aria-label={`重试上传 ${item.file.name}`}
                    onClick={() => void draft.retry(item)}
                  >
                    <RotateCcw className="size-3" />
                    重试
                  </Button>
                ) : null}
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                disabled={disabled}
                className="absolute top-1 right-1 size-7 min-h-7"
                aria-label={`移除 ${item.file.name}`}
                onClick={() => draft.remove(item.key)}
              >
                <X className="size-3.5" />
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
      {children}
      <div className="mt-2 flex items-center gap-2">
        <input
          ref={input}
          type="file"
          className="sr-only"
          tabIndex={-1}
          aria-label="上传聊天附件"
          accept={ATTACHMENT_ACCEPT}
          multiple
          disabled={disabled}
          onChange={(event) => {
            draft.add(Array.from(event.target.files ?? []));
            event.target.value = "";
          }}
        />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="size-9 min-h-9 rounded-full bg-sidebar"
              aria-label="添加附件"
              disabled={disabled || draft.items.length >= 6}
            >
              <Plus className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side="top" className="w-56">
            <DropdownMenuItem onSelect={() => input.current?.click()}>
              <Paperclip className="size-4" />
              上传文件
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <p className="min-w-0 flex-1 text-[11px] text-muted-foreground">
          图片 / PDF / DOCX / TXT / Markdown · 最多 6 件
        </p>
        {actions}
      </div>
      {draft.notice ? (
        <p role="alert" className="mt-2 text-xs text-destructive">
          {draft.notice}
        </p>
      ) : null}
    </div>
  );
}
