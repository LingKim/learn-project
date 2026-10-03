"use client";
import { useQuery } from "@tanstack/react-query";
import {
  Bell,
  BookOpenText,
  CalendarDays,
  ClipboardList,
  Library,
  Mic,
  NotebookPen,
  Settings,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { AccountControl } from "@/features/auth/account-control";
import { NavigationSettings } from "@/features/user-profile/navigation-settings";
import { userProfileQueryOptions } from "@/features/user-profile/queries";
import { cn } from "@/lib/utils";
const navigation = [
  { href: "/learning", label: "学习室", icon: Sparkles },
  { href: null, label: "面试间", icon: Mic },
  { href: "/content", label: "内容库", icon: Library },
  { href: "/weaknesses", label: "难点", icon: BookOpenText },
  { href: null, label: "笔记本", icon: NotebookPen },
  { href: null, label: "学习计划", icon: CalendarDays },
] as const;
function NavigationHint({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side="right" sideOffset={8}>
        {label}
      </TooltipContent>
    </Tooltip>
  );
}
export function ContentShell({ children }: Readonly<{ children: ReactNode }>) {
  const pathname = usePathname();
  const profile = useQuery(userProfileQueryOptions());
  const left = profile.data?.navigation_position !== "top";
  const [settingsOpen, setSettingsOpen] = useState(false);
  const itemClass =
    "nav-item inline-flex size-10 shrink-0 cursor-pointer items-center justify-center gap-2 rounded-[7px] text-[13px] font-medium transition-colors hover:bg-sidebar focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary motion-reduce:transition-none";
  return (
    <TooltipProvider delayDuration={150}>
      <main data-navigation={left ? "left" : "top"} className="app-shell min-h-dvh bg-background">
        <header aria-label="全局导航" className="app-navigation z-30 border-border bg-surface">
          <NavigationHint label="学面通AI · 工程状态">
            <Link
              href="/"
              className="nav-brand flex size-10 shrink-0 cursor-pointer items-center justify-center gap-2.5 rounded-[7px] focus-visible:outline-2 focus-visible:outline-primary"
              aria-label="学面通AI · 工程状态"
            >
              <span className="grid size-9 place-items-center rounded-[9px] bg-primary text-primary-foreground">
                <BookOpenText aria-hidden="true" className="size-5" />
              </span>
              <span className="nav-label text-[18px] font-bold">学面通AI</span>
            </Link>
          </NavigationHint>
          <nav aria-label="主要导航" className="nav-primary flex min-w-0 gap-1">
            {navigation.map(({ href, label, icon: Icon }) => (
              <NavigationHint key={label} label={href ? label : `${label} · 尚未开放`}>
                {href ? (
                  <Link
                    href={href}
                    aria-label={label}
                    aria-current={pathname.startsWith(href) ? "page" : undefined}
                    className={cn(
                      itemClass,
                      pathname.startsWith(href)
                        ? "bg-muted text-foreground"
                        : "text-muted-foreground",
                    )}
                  >
                    <Icon aria-hidden="true" className="size-5 shrink-0" />
                    <span className="nav-label">{label}</span>
                  </Link>
                ) : (
                  <button
                    type="button"
                    aria-disabled="true"
                    aria-label={`${label}（尚未开放）`}
                    className={cn(itemClass, "cursor-not-allowed text-muted-foreground")}
                  >
                    <Icon aria-hidden="true" className="size-5 shrink-0" />
                    <span className="nav-label">{label}</span>
                  </button>
                )}
              </NavigationHint>
            ))}
          </nav>
          <div className="nav-secondary flex shrink-0 items-center gap-2">
            {(
              [
                ["任务中心", ClipboardList],
                ["通知", Bell],
              ] as const
            ).map(([label, Icon]) => (
              <NavigationHint key={label} label={`${label} · 尚未开放`}>
                <button
                  type="button"
                  aria-disabled="true"
                  aria-label={`${label}（尚未开放）`}
                  className={cn(
                    itemClass,
                    "nav-unavailable cursor-not-allowed text-muted-foreground",
                  )}
                >
                  <Icon aria-hidden="true" className="size-5" />
                </button>
              </NavigationHint>
            ))}
            <NavigationHint label="用户设置">
              <button
                type="button"
                aria-label="用户设置"
                className={itemClass}
                onClick={() => setSettingsOpen(true)}
              >
                <Settings aria-hidden="true" className="size-5" />
              </button>
            </NavigationHint>
            <div className="nav-account">
              <AccountControl compact={left} />
            </div>
          </div>
        </header>
        <div className="min-w-0 flex-1">{children}</div>
        {settingsOpen && <NavigationSettings open onOpenChange={setSettingsOpen} />}
      </main>
    </TooltipProvider>
  );
}
