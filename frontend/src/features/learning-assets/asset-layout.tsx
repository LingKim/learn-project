"use client";

import Link from "next/link";
import { BookOpenText, ClipboardCheck, MessageCircle } from "lucide-react";
import type { ReactNode } from "react";
import { ContentShell } from "@/features/file-management/content-shell";
import { cn } from "@/lib/utils";

export function AssetLayout({ children }: { children: ReactNode }) {
  return (
    <ContentShell>
      <section className="min-w-0 px-4 py-6 sm:px-8 xl:px-11">{children}</section>
    </ContentShell>
  );
}

export function ExplanationModes() {
  return (
    <nav
      aria-label="学习模式"
      className="grid min-w-0 grid-cols-3 gap-[5px] rounded-[9px] border border-border bg-sidebar p-[5px]"
    >
      {[
        { href: "/learning", title: "快速回答", text: "即时解答与追问", Icon: MessageCircle },
        {
          href: "/learning/explanation",
          title: "知识精讲",
          text: "结构化讲透知识点",
          Icon: BookOpenText,
        },
        {
          href: "/learning/practice",
          title: "刷题练习",
          text: "创建题目并评估能力",
          Icon: ClipboardCheck,
        },
      ].map(({ href, title, text, Icon }) => (
        <Link
          key={href}
          href={href}
          aria-current={title === "知识精讲" ? "page" : undefined}
          className={cn(
            "flex min-h-12 min-w-0 items-center justify-center gap-2 rounded-md px-2 text-[13px]",
            title === "知识精讲"
              ? "border border-border bg-surface font-semibold shadow-sm"
              : "text-muted-foreground hover:bg-surface",
          )}
        >
          <Icon aria-hidden="true" className="size-4 shrink-0" />
          <span className="min-w-0">
            <span className="block">{title}</span>
            <span className="hidden text-[11px] font-normal sm:block">{text}</span>
          </span>
        </Link>
      ))}
    </nav>
  );
}

export function AssetEmpty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="my-5 border-t border-border py-10 text-center">
      <BookOpenText aria-hidden="true" className="mx-auto mb-3 size-7 text-muted-foreground" />
      <p className="text-sm font-semibold">{title}</p>
      <div className="mt-3 text-sm text-muted-foreground">{children}</div>
    </div>
  );
}

export const masteryLabels = {
  to_learn: "待学习",
  learning: "学习中",
  to_verify: "待验证",
  mastered: "已掌握",
};
export const severityLabels = { low: "低", medium: "中", high: "高" };
export const foundationLabels = {
  unfamiliar: "完全不了解",
  know_concept: "知道概念",
  used_unfamiliar: "用过但不熟",
  review: "查漏补缺",
};
export const depthLabels = { quick: "快速理解", systematic: "系统掌握", deep: "深入原理" };
export const sectionLabels = [
  "概念与适用场景",
  "原理与执行过程",
  "代码或业务示例",
  "常见误区与边界",
  "理解练习",
];

export function practiceTargetHref(kind: "weakness" | "explanation", id: string, version: number) {
  const params = new URLSearchParams(
    kind === "weakness"
      ? { weakness: id, version: String(version) }
      : { explanation: id, card: String(version) },
  );
  return `/learning/practice?${params.toString()}`;
}
