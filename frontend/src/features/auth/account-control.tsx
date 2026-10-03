"use client";

import Link from "next/link";
import { LogOut, UserRound } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

import { useAuth } from "./auth-provider";

export function AccountControl({ compact = false }: { compact?: boolean }) {
  const { user, logout } = useAuth();
  const [pending, setPending] = useState(false);

  async function handleLogout() {
    setPending(true);
    try {
      await logout();
    } finally {
      setPending(false);
    }
  }

  return (
    <div className={compact ? "flex flex-col items-center gap-2" : "flex items-center gap-2"}>
      <Tooltip>
        <TooltipTrigger asChild>
          <Link
            href="/profile"
            aria-label="个人资料"
            title={user?.nickname ? `个人资料 · ${user.nickname}` : "个人资料"}
            className="grid size-9 place-items-center rounded-[7px] bg-sidebar text-muted-foreground hover:bg-muted cursor-pointer focus-visible:outline-2 focus-visible:outline-primary"
          >
            <UserRound className="size-4" />
          </Link>
        </TooltipTrigger>
        <TooltipContent side="right" sideOffset={8}>
          个人资料
        </TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-label={pending ? "正在退出" : "退出登录"}
            title="退出登录"
            disabled={pending}
            onClick={handleLogout}
          >
            <LogOut aria-hidden="true" />
            <span className="sr-only">{pending ? "正在退出" : "退出登录"}</span>
          </Button>
        </TooltipTrigger>
        <TooltipContent side="right" sideOffset={8}>
          退出登录
        </TooltipContent>
      </Tooltip>
    </div>
  );
}
