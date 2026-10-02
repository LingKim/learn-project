"use client";

import Link from "next/link";
import { LogOut, UserRound } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

import { useAuth } from "./auth-provider";

export function AccountControl() {
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
    <div className="flex items-center gap-2">
      <Link
        href="/profile"
        aria-label="个人资料"
        title={user?.nickname ? `个人资料 · ${user.nickname}` : "个人资料"}
        className="grid size-9 place-items-center rounded-[7px] bg-sidebar text-muted-foreground hover:bg-muted"
      >
        <UserRound className="size-4" />
      </Link>

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
    </div>
  );
}
