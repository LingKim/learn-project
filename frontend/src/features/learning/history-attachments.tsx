"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileText, ImageIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import type { LearningAttachmentView } from "./api";
import { attachmentContentQueryOptions } from "./queries";

function AttachmentPreview({ attachment }: { attachment: LearningAttachmentView }) {
  const content = useQuery(attachmentContentQueryOptions(attachment.id));
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!content.data) return;
    const objectUrl = URL.createObjectURL(content.data);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [content.data]);
  if (content.isPending) return <p role="status">正在读取附件…</p>;
  if (content.isError)
    return (
      <p role="alert">
        附件读取失败。
        <Button variant="ghost" onClick={() => void content.refetch()}>
          重试
        </Button>
      </p>
    );
  if (!url) return null;
  return attachment.kind === "image" ? (
    <img src={url} alt={attachment.filename} className="max-h-[70dvh] w-full object-contain" />
  ) : (
    <a className="text-sm underline" href={url} download={attachment.filename}>
      下载 {attachment.filename}
    </a>
  );
}
export function HistoryAttachments({ attachments }: { attachments: LearningAttachmentView[] }) {
  const [preview, setPreview] = useState<LearningAttachmentView | null>(null);
  if (!attachments.length) return null;
  return (
    <>
      <div className="mb-2 flex flex-wrap justify-end gap-2" aria-label="已发送附件">
        {attachments.map((attachment) => (
          <Button
            key={attachment.id}
            type="button"
            variant="outline"
            size="sm"
            className="max-w-full"
            onClick={() => setPreview(attachment)}
          >
            {attachment.kind === "image" ? (
              <ImageIcon className="size-4 shrink-0" />
            ) : (
              <FileText className="size-4 shrink-0" />
            )}
            <span className="max-w-52 truncate">{attachment.filename}</span>
          </Button>
        ))}
      </div>
      <Dialog
        open={Boolean(preview)}
        onOpenChange={(open) => {
          if (!open) setPreview(null);
        }}
      >
        <DialogContent className="max-w-3xl">
          <DialogTitle>附件预览</DialogTitle>
          <DialogDescription>{preview?.filename}</DialogDescription>
          {preview ? <AttachmentPreview key={preview.id} attachment={preview} /> : null}
        </DialogContent>
      </Dialog>
    </>
  );
}
