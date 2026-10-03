"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";

// 浏览器资源不经过业务 API，也不会向外站附加我们的 Authorization。
export function safeAnswerUrl(value: string | undefined): string | undefined {
  if (!value) return undefined;
  const url = value.trim();
  if (
    !url ||
    Array.from(url).some((character) => {
      const code = character.charCodeAt(0);
      return code <= 32 || code === 127 || character === "\\";
    })
  )
    return undefined;
  try {
    const parsed = new URL(url, "https://answer.local/");
    if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password)
      return undefined;
    // 协议相对地址不能悄悄把相对资源指向外站。
    if (url.startsWith("//")) return undefined;
    return url;
  } catch {
    return undefined;
  }
}

export function answerMediaKind(url: string): "image" | "video" | "audio" | undefined {
  const path = new URL(url, "https://answer.local/").pathname.toLowerCase();
  if (/\.(?:png|jpe?g|gif|webp|avif)$/.test(path)) return "image";
  if (/\.(?:mp4|webm|ogv|mov)$/.test(path)) return "video";
  if (/\.(?:mp3|wav|ogg|m4a|aac|flac)$/.test(path)) return "audio";
  return undefined;
}

export function AnswerImage({ src, alt }: { src?: string; alt?: string }) {
  const [preview, setPreview] = useState(false);
  const [failed, setFailed] = useState(false);
  const safeSrc = safeAnswerUrl(src);
  const description = alt || "回答中的图片";
  if (!safeSrc || failed) return <span role="status">图片无法加载：{description}</span>;
  return (
    <>
      <button
        type="button"
        className="my-2 inline-flex max-w-full rounded-md focus-visible:outline-2 focus-visible:outline-ring"
        aria-label={`放大图片：${description}`}
        onClick={() => setPreview(true)}
      >
        <img
          src={safeSrc}
          alt={description}
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
          className="max-h-80 max-w-full rounded-md object-contain"
        />
      </button>
      <Dialog open={preview} onOpenChange={setPreview}>
        <DialogContent className="max-w-5xl">
          <DialogTitle>图片预览</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
          <img
            src={safeSrc}
            alt={description}
            referrerPolicy="no-referrer"
            onError={() => setFailed(true)}
            className="max-h-[75dvh] w-full object-contain"
          />
        </DialogContent>
      </Dialog>
    </>
  );
}

export function AnswerPlayer({
  kind,
  src,
  label,
  sources = [],
}: {
  kind: "audio" | "video";
  src?: string;
  label?: string;
  sources?: Array<{ src?: string; type?: string }>;
}) {
  const [failed, setFailed] = useState(false);
  const safeSrc = safeAnswerUrl(src);
  const safeSources = sources.flatMap((source) => {
    const safe = safeAnswerUrl(source.src);
    return safe ? [{ src: safe, type: source.type }] : [];
  });
  const description = label || (kind === "video" ? "回答中的视频" : "回答中的音频");
  if (failed || (!safeSrc && !safeSources.length))
    return (
      <span role="status">
        {kind === "video" ? "视频" : "音频"}无法加载：{description}
      </span>
    );
  const Element = kind;
  return (
    <span className="my-3 block max-w-full">
      <Element
        src={safeSrc}
        controls
        preload="none"
        aria-label={description}
        onError={() => setFailed(true)}
        className="max-h-96 w-full rounded-md"
      >
        {safeSources.map((source) => (
          <source key={source.src} {...source} />
        ))}
        您的浏览器不支持播放此媒体。
      </Element>
    </span>
  );
}
