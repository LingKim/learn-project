"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import type { LearningAttachmentView } from "./api";
import { uploadAttachmentMutationOptions, deleteAttachmentMutationOptions } from "./queries";

export const ATTACHMENT_ACCEPT = ".png,.jpg,.jpeg,.webp,.pdf,.docx,.txt,.md,.markdown";
export type DraftAttachment = {
  key: string;
  file: File;
  preview?: string;
  status: "uploading" | "ready" | "error";
  attachment?: LearningAttachmentView;
  error?: string;
};
export function attachmentValidation(file: File) {
  const image = /\.(png|jpe?g|webp)$/i.test(file.name);
  if (!image && !/\.(pdf|docx|txt|md|markdown)$/i.test(file.name))
    return "支持 PNG/JPG/WebP、PDF/DOCX/TXT/Markdown。";
  if (!file.size) return "文件为空，请选择有内容的文件。";
  if (file.size > (image ? 5 : 10) * 1024 * 1024)
    return image ? "图片不能超过 5 MB。" : "文档不能超过 10 MB。";
  return null;
}
export function useDraftAttachments() {
  const [items, setItems] = useState<DraftAttachment[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const current = useRef<DraftAttachment[]>([]);
  const upload = useMutation(uploadAttachmentMutationOptions());
  const removeRemote = useMutation(deleteAttachmentMutationOptions());
  const deleteRef = useRef(removeRemote.mutateAsync);
  deleteRef.current = removeRemote.mutateAsync;
  function update(next: DraftAttachment[]) {
    current.current = next;
    setItems(next);
  }
  function discard(item: DraftAttachment, deleteServer = true) {
    if (item.preview) URL.revokeObjectURL(item.preview);
    if (deleteServer && item.attachment)
      void deleteRef
        .current(item.attachment.id)
        .catch(() => setNotice("附件清理失败，请稍后重试；未发送附件会自动过期。"));
  }
  async function perform(item: DraftAttachment) {
    update(
      current.current.map((value) =>
        value.key === item.key ? { ...value, status: "uploading", error: undefined } : value,
      ),
    );
    try {
      const result = await upload.mutateAsync(item.file);
      if (!current.current.some((value) => value.key === item.key)) {
        await deleteRef.current(result.data.id);
        return;
      }
      update(
        current.current.map((value) =>
          value.key === item.key ? { ...value, status: "ready", attachment: result.data } : value,
        ),
      );
    } catch (error) {
      update(
        current.current.map((value) =>
          value.key === item.key
            ? {
                ...value,
                status: "error",
                error: error instanceof Error ? error.message : "上传失败，请重试。",
              }
            : value,
        ),
      );
    }
  }
  function add(files: File[]) {
    setNotice(null);
    for (const file of files) {
      if (current.current.length >= 6) {
        setNotice("每次最多上传 6 个附件。");
        break;
      }
      const invalid = attachmentValidation(file);
      if (invalid) {
        setNotice(`${file.name}：${invalid}`);
        continue;
      }
      const item: DraftAttachment = {
        key: crypto.randomUUID(),
        file,
        status: "uploading",
        preview: /\.(png|jpe?g|webp)$/i.test(file.name) ? URL.createObjectURL(file) : undefined,
      };
      update([...current.current, item]);
      void perform(item);
    }
  }
  function remove(key: string) {
    const item = current.current.find((value) => value.key === key);
    update(current.current.filter((value) => value.key !== key));
    if (item) discard(item);
  }
  function clear(deleteServer = true) {
    const old = current.current;
    update([]);
    old.forEach((item) => discard(item, deleteServer));
    setNotice(null);
  }
  function acknowledge(ids: string[]) {
    const sent = current.current.filter(
      (item) => item.attachment && ids.includes(item.attachment.id),
    );
    update(current.current.filter((item) => !sent.includes(item)));
    sent.forEach((item) => discard(item, false));
  }
  useEffect(
    () => () => {
      const old = current.current;
      current.current = [];
      old.forEach((item) => {
        if (item.preview) URL.revokeObjectURL(item.preview);
        if (item.attachment) void deleteRef.current(item.attachment.id).catch(() => undefined);
      });
    },
    [],
  );
  return {
    items,
    notice,
    add,
    remove,
    clear,
    acknowledge,
    retry: perform,
    ready: items.filter((item) => item.status === "ready").map((item) => item.attachment!),
    blocked: items.some((item) => item.status !== "ready"),
  };
}
