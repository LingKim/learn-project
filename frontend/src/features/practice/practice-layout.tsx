"use client";

import Link from "next/link";
import { BookOpenText, ClipboardCheck, MessageCircle, Plus } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { ContentShell } from "@/features/file-management/content-shell";

/** Pen 68 / 70 / 73: current global navigation, 220px private history and warm main area. */
export function PracticeLayout({
  children,
  history,
  answerMode = false,
}: {
  children: ReactNode;
  history: ReactNode;
  answerMode?: boolean;
}) {
  return (
    <ContentShell>
      <div className="flex min-h-dvh min-w-0 flex-col lg:flex-row">
        {!answerMode ? (
          <aside
            aria-label="我的练习"
            className="flex shrink-0 flex-col gap-[18px] border-b border-border bg-sidebar px-[18px] py-6 lg:w-[220px] lg:border-r lg:border-b-0"
          >
            <h2 className="text-[17px] font-bold">我的练习</h2>
            <Button asChild variant="brand" className="h-10 min-h-10">
              <Link href="/learning/practice">
                <Plus aria-hidden="true" className="size-4" />
                新建练习
              </Link>
            </Button>
            {history}
          </aside>
        ) : null}
        <section
          className={answerMode ? "min-w-0 flex-1" : "min-w-0 flex-1 px-4 py-6 sm:px-8 xl:px-12"}
        >
          {children}
        </section>
      </div>
    </ContentShell>
  );
}

export function PracticeModes() {
  return (
    <nav
      aria-label="学习模式"
      className="grid min-w-0 grid-cols-3 gap-[5px] rounded-[9px] border border-border bg-sidebar p-[5px]"
    >
      <Link
        href="/learning"
        className="flex min-h-[48px] min-w-0 items-center justify-center gap-2 rounded-md px-2 text-[13px] text-muted-foreground hover:bg-surface"
      >
        <MessageCircle aria-hidden="true" className="size-4 shrink-0" />
        <span className="min-w-0">
          <span className="block">快速回答</span>
          <span className="hidden text-[11px] sm:block">即时解答与追问</span>
        </span>
      </Link>
      <button
        type="button"
        disabled
        className="flex min-h-[48px] min-w-0 items-center justify-center gap-2 rounded-md px-2 text-[13px] text-muted-foreground"
        aria-label="知识精讲（尚未开放）"
      >
        <BookOpenText aria-hidden="true" className="size-4 shrink-0" />
        <span className="min-w-0">
          <span className="block">知识精讲</span>
          <span className="hidden text-[11px] sm:block">结构化讲透知识点</span>
        </span>
      </button>
      <button
        type="button"
        aria-current="page"
        className="flex min-h-[48px] min-w-0 items-center justify-center gap-2 rounded-md border border-border bg-surface px-2 text-[13px] font-semibold shadow-sm"
      >
        <ClipboardCheck aria-hidden="true" className="size-4 shrink-0" />
        <span className="min-w-0">
          <span className="block">刷题练习</span>
          <span className="hidden text-[11px] font-normal sm:block">创建题目并评估能力</span>
        </span>
      </button>
    </nav>
  );
}
