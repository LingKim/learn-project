"use client";

import { BookOpenText, Library, Sparkles, UserRound } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { AccountControl } from "@/features/auth/account-control";
import { cn } from "@/lib/utils";

const navigation = [
  { href: "/", label: "工程状态", icon: Sparkles },
  { href: "/content", label: "内容库", icon: Library },
  { href: "/profile", label: "个人资料", icon: UserRound },
] as const;

export function ContentShell({ children }: Readonly<{ children: ReactNode }>) {
  const pathname = usePathname();

  return (
    <main className="min-h-dvh bg-background">
      <header className="sticky top-0 z-30 border-b border-border bg-surface/95 backdrop-blur-sm">
        <div className="mx-auto flex min-h-[4.75rem] max-w-[90rem] items-center justify-between gap-4 px-4 sm:px-8">
          <div className="flex min-w-0 items-center gap-5 lg:gap-10">
            <Link href="/" className="flex shrink-0 items-center gap-2.5">
              <span className="grid size-9 place-items-center rounded-lg bg-primary text-primary-foreground">
                <BookOpenText aria-hidden="true" className="size-[1.15rem]" strokeWidth={2.2} />
              </span>
              <span className="hidden text-base font-bold tracking-[-0.02em] sm:inline">
                学面通AI
              </span>
            </Link>
            <nav aria-label="主要导航" className="flex items-center gap-1">
              {navigation.map(({ href, label, icon: Icon }) => {
                const active = href === "/" ? pathname === href : pathname.startsWith(href);
                return (
                  <Link
                    key={href}
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "inline-flex min-h-10 items-center gap-2 rounded-md px-3 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-ring",
                      active
                        ? "bg-primary/35 text-foreground"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    <Icon aria-hidden="true" className="size-4" />
                    {label}
                  </Link>
                );
              })}
            </nav>
          </div>
          <AccountControl />
        </div>
      </header>
      {children}
    </main>
  );
}
