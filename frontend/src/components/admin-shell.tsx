"use client";

import { ShieldCheck, ScanSearch, ListChecks, FileCode2 } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { AccountControl } from "@/features/auth/account-control";
import { cn } from "@/lib/utils";

const links = [
  { href: "/admin/prompts", label: "提示词管理", icon: FileCode2 },
  { href: "/admin/ai-quality", label: "质量诊断", icon: ScanSearch },
  { href: "/admin/ai-quality/cases", label: "工单队列", icon: ListChecks },
] as const;

export function AdminShell({ children }: Readonly<{ children: ReactNode }>) {
  const pathname = usePathname();
  return (
    <main className="min-h-dvh bg-background">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b bg-surface px-5 py-4 lg:px-8">
        <Link href="/" className="flex items-center gap-3" aria-label="学面通AI首页">
          <span className="grid size-9 place-items-center rounded-[9px] bg-primary">
            <ShieldCheck className="size-5" aria-hidden="true" />
          </span>
          <span>
            <strong className="block text-sm">学面通AI</strong>
            <span className="text-xs text-muted-foreground">系统管理台</span>
          </span>
        </Link>
        <nav aria-label="管理导航" className="flex flex-wrap gap-2">
          {links.map(({ href, label, icon: Icon }) => {
            const active =
              href === "/admin/ai-quality" ? pathname === href : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "inline-flex items-center gap-2 rounded-[7px] px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-primary",
                  active ? "bg-muted" : "text-muted-foreground hover:bg-sidebar",
                )}
              >
                <Icon className="size-4" aria-hidden="true" />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">系统管理员</span>
          <AccountControl />
        </div>
      </header>
      {children}
    </main>
  );
}
