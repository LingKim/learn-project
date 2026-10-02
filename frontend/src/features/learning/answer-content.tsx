import { Fragment } from "react";

// 只渲染文本与代码围栏，不解释用户或模型提供的 HTML/脚本/链接。
export function AnswerContent({ content }: { content: string }) {
  return (
    <div className="space-y-3 text-[13px] leading-6">
      {content.split(/(```[\s\S]*?```)/g).map((part, index) =>
        part.startsWith("```") ? (
          <pre
            key={index}
            className="overflow-x-auto rounded border border-border bg-surface p-3 text-xs"
          >
            <code>{part.replace(/^```[^\n]*\n?/, "").replace(/```$/, "")}</code>
          </pre>
        ) : (
          <Fragment key={index}>
            {part.split(/\n\s*\n/).map((paragraph, p) => (
              <p key={p} className="whitespace-pre-wrap break-words">
                {paragraph.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).map((text, t) =>
                  text.startsWith("**") ? (
                    <strong key={t}>{text.slice(2, -2)}</strong>
                  ) : text.startsWith("`") ? (
                    <code key={t} className="rounded bg-surface px-1 text-xs">
                      {text.slice(1, -1)}
                    </code>
                  ) : (
                    text
                  ),
                )}
              </p>
            ))}
          </Fragment>
        ),
      )}
    </div>
  );
}
