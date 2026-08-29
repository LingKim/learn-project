import { ArrowUpRight, BookOpenText, Library } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { AccountControl } from "@/features/auth/account-control";
import { ProtectedRoute } from "@/features/auth/auth-route";
import { SystemHealthPanel } from "@/features/system-health/system-health-panel";

export default function Home() {
  return (
    <ProtectedRoute>
      <main className="min-h-dvh px-4 py-4 sm:px-6 sm:py-6 lg:px-10 lg:py-8">
        <div className="mx-auto flex min-h-[calc(100dvh-2rem)] max-w-[90rem] flex-col overflow-hidden rounded-[1.25rem] border border-border bg-surface sm:min-h-[calc(100dvh-3rem)]">
          <header className="flex min-h-16 items-center justify-between gap-4 border-b border-border px-5 sm:px-8">
            <div className="flex items-center gap-3">
              <span className="grid size-9 place-items-center rounded-md bg-primary text-primary-foreground">
                <BookOpenText aria-hidden="true" className="size-[1.125rem]" strokeWidth={2.2} />
              </span>
              <div>
                <p className="text-base font-semibold tracking-[-0.02em] text-foreground">
                  学面通AI
                </p>
                <p className="text-xs text-muted-foreground">工程基线 · 系统状态</p>
              </div>
            </div>
            <AccountControl />
          </header>

          <div className="grid flex-1 lg:grid-cols-[minmax(0,1.2fr)_minmax(24rem,0.8fr)]">
            <section className="relative flex flex-col justify-between overflow-hidden border-b border-border px-6 py-10 sm:px-10 sm:py-14 lg:border-r lg:border-b-0 lg:px-14 lg:py-16">
              <div
                className="pointer-events-none absolute top-10 right-10 grid grid-cols-5 gap-2 opacity-45"
                aria-hidden="true"
              >
                {Array.from({ length: 20 }, (_, index) => (
                  <span key={index} className="size-1 rounded-full bg-primary" />
                ))}
              </div>

              <div className="relative max-w-[42rem]">
                <Badge variant="warm">准备开始</Badge>
                <h1 className="mt-8 max-w-[12ch] text-[clamp(2.6rem,6vw,5.75rem)] leading-[0.98] font-semibold tracking-[-0.065em] text-foreground">
                  先确认地基，<span className="text-accent-foreground">再专注成长。</span>
                </h1>
                <p className="mt-7 max-w-[34rem] text-base leading-7 text-muted-foreground sm:text-lg sm:leading-8">
                  这是学面通AI的工程就绪页。它只验证前端、API
                  与基础依赖是否连接，不代表任何学习或面试业务已经上线。
                </p>
              </div>

              <div className="relative mt-14 flex flex-wrap items-center gap-x-6 gap-y-3 text-sm text-muted-foreground">
                <Link
                  href="/content"
                  className="inline-flex min-h-11 items-center gap-2 rounded-md bg-primary px-4 font-semibold text-primary-foreground transition-colors hover:bg-[color-mix(in_oklch,var(--primary),var(--foreground)_10%)] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring"
                >
                  <Library aria-hidden="true" className="size-4" />
                  进入内容库
                </Link>
                <span className="inline-flex items-center gap-2">
                  <span className="size-2 rounded-full bg-primary" />
                  OpenAPI 驱动契约
                </span>
                <a
                  href="/api/backend/docs"
                  className="inline-flex min-h-11 items-center gap-1.5 font-medium text-foreground underline decoration-border underline-offset-4 transition-colors hover:text-accent-foreground focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring"
                >
                  查看 API 文档
                  <ArrowUpRight aria-hidden="true" className="size-4" />
                </a>
              </div>
            </section>

            <section className="flex items-center bg-sidebar px-5 py-10 sm:px-10 lg:px-12">
              <SystemHealthPanel />
            </section>
          </div>
        </div>
      </main>
    </ProtectedRoute>
  );
}
