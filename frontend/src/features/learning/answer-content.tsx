"use client";

import { memo } from "react";
import ReactMarkdown, { type Components, type ExtraProps } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import { AnswerImage, AnswerPlayer, answerMediaKind, safeAnswerUrl } from "./answer-media";

const mediaSchema = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames ?? []), "audio", "video", "source"],
  attributes: {
    ...defaultSchema.attributes,
    audio: ["src", "title"],
    video: ["src", "title"],
    source: ["src", "type"],
  },
};
const components: Components = {
  // div 避免 Markdown 的图片/播放器嵌套在 p 内造成无效 HTML。
  p: ({ children }) => <div className="my-3 whitespace-pre-wrap break-words">{children}</div>,
  h1: ({ children }) => <h1 className="mt-5 mb-3 text-xl font-semibold">{children}</h1>,
  h2: ({ children }) => <h2 className="mt-5 mb-2 text-lg font-semibold">{children}</h2>,
  h3: ({ children }) => <h3 className="mt-4 mb-2 text-base font-semibold">{children}</h3>,
  ul: ({ children }) => <ul className="my-3 list-disc space-y-1 pl-6">{children}</ul>,
  ol: ({ children }) => <ol className="my-3 list-decimal space-y-1 pl-6">{children}</ol>,
  blockquote: ({ children }) => (
    <blockquote className="my-3 border-l-2 border-primary pl-4 text-muted-foreground">
      {children}
    </blockquote>
  ),
  pre: ({ children }) => (
    <pre className="my-3 max-w-full overflow-x-auto rounded-md border border-border bg-surface p-3 text-xs leading-6">
      {children}
    </pre>
  ),
  code: ({ children, className }) => (
    <code className={className || "rounded bg-surface px-1 font-mono text-[0.9em]"}>
      {children}
    </code>
  ),
  table: ({ children }) => (
    <div className="my-3 max-w-full overflow-x-auto">
      <table className="w-full border-collapse text-left text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-border bg-surface px-3 py-2 font-semibold">{children}</th>
  ),
  td: ({ children }) => <td className="border border-border px-3 py-2 align-top">{children}</td>,
  img: ({ src, alt }) => (
    <AnswerImage
      key={typeof src === "string" ? src : "invalid"}
      src={typeof src === "string" ? src : undefined}
      alt={alt}
    />
  ),
  a: ({ href, children }) => {
    const safe = safeAnswerUrl(href);
    if (!safe) return <span>{children}</span>;
    const kind = answerMediaKind(safe);
    if (kind === "image")
      return (
        <AnswerImage
          key={safe}
          src={safe}
          alt={typeof children === "string" ? children : undefined}
        />
      );
    if (kind)
      return (
        <AnswerPlayer
          kind={kind}
          key={safe}
          src={safe}
          label={typeof children === "string" ? children : undefined}
        />
      );
    return (
      <a
        href={safe}
        target="_blank"
        rel="noopener noreferrer"
        className="break-all text-foreground underline decoration-primary underline-offset-4"
      >
        {children}
      </a>
    );
  },
  video: ({ src, title, node }) => (
    <AnswerPlayer
      kind="video"
      key={JSON.stringify([src, mediaSources(node)])}
      src={typeof src === "string" ? src : undefined}
      label={title}
      sources={mediaSources(node)}
    />
  ),
  audio: ({ src, title, node }) => (
    <AnswerPlayer
      kind="audio"
      key={JSON.stringify([src, mediaSources(node)])}
      src={typeof src === "string" ? src : undefined}
      label={title}
      sources={mediaSources(node)}
    />
  ),
};

function mediaSources(node: ExtraProps["node"]) {
  return (
    node?.children.flatMap((child) => {
      if (child.type !== "element" || child.tagName !== "source") return [];
      return [
        {
          src: typeof child.properties.src === "string" ? child.properties.src : undefined,
          type: typeof child.properties.type === "string" ? child.properties.type : undefined,
        },
      ];
    }) ?? []
  );
}

export const AnswerContent = memo(function AnswerContent({ content }: { content: string }) {
  return (
    <div className="min-w-0 text-sm leading-7 [overflow-wrap:anywhere] [&_hr]:my-4 [&_hr]:border-border">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw, [rehypeSanitize, mediaSchema]]}
        components={components}
        urlTransform={(url) => safeAnswerUrl(url) ?? ""}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
});
