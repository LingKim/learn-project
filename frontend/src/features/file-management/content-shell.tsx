"use client";

import {
  Bell,
  BookOpenText,
  CalendarDays,
  ClipboardList,
  Library,
  Mic,
  NotebookPen,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { AccountControl } from "@/features/auth/account-control";
import { cn } from "@/lib/utils";

const navigation = [
  { href: "/learning", label: "学习室", icon: Sparkles },
  { href: null, label: "面试间", icon: Mic },
  { href: "/content", label: "内容库", icon: Library },
  { href: null, label: "难点", icon: BookOpenText },
  { href: null, label: "笔记本", icon: NotebookPen },
  { href: null, label: "学习计划", icon: CalendarDays },
] as const;

export function ContentShell({ children }: Readonly<{ children: ReactNode }>) {
  const pathname = usePathname();
  return (
    <main className="min-h-dvh bg-background">
      <header className="relative z-30 border-b border-border bg-surface">
        <div className="flex min-h-[75px] items-center justify-between gap-4 px-4 sm:px-8">
          <Link
            href="/"
            className="flex shrink-0 items-center gap-2.5"
            aria-label="学面通AI · 工程状态"
          >
            <span className="grid size-9 place-items-center rounded-[9px] bg-primary text-primary-foreground">
              <BookOpenText aria-hidden="true" className="size-5" />
            </span>
            <span className="hidden text-[18px] font-bold sm:inline">学面通AI</span>
          </Link>
          <nav aria-label="主要导航" className="flex min-w-0 items-center gap-1 overflow-x-auto">
            {navigation.map(({ href, label, icon: Icon }) => {
              const classes =
                "inline-flex h-10 shrink-0 items-center gap-[7px] rounded-[7px] px-3 text-[13px] font-medium";
              return href ? (
                <Link
                  key={label}
                  href={href}
                  aria-current={pathname.startsWith(href) ? "page" : undefined}
                  className={cn(
                    classes,
                    pathname.startsWith(href)
                      ? "bg-muted text-foreground"
                      : "text-muted-foreground hover:bg-sidebar",
                  )}
                >
                  <Icon aria-hidden="true" className="size-4" />
                  {label}
                </Link>
              ) : (
                <button
                  key={label}
                  disabled
                  title={`${label}尚未开放`}
                  aria-label={`${label}（尚未开放）`}
                  className={cn(classes, "text-muted-foreground disabled:cursor-not-allowed")}
                >
                  <Icon aria-hidden="true" className="size-4" />
                  {label}
                </button>
              );
            })}
          </nav>
          <div className="flex shrink-0 items-center gap-2">
            <button
              disabled
              title="任务中心尚未开放"
              aria-label="任务中心（尚未开放）"
              className="hidden h-9 items-center gap-2 px-2 text-xs text-muted-foreground xl:flex"
            >
              <ClipboardList className="size-4" />
              任务中心
            </button>
            <button
              disabled
              title="通知尚未开放"
              aria-label="通知（尚未开放）"
              className="hidden size-9 place-items-center rounded-[7px] bg-sidebar text-muted-foreground lg:grid"
            >
              <Bell className="size-4" />
            </button>
            <AccountControl />
          </div>
        </div>
      </header>
      {children}
    </main>
  );
}
