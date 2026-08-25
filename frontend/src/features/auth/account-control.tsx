"use client";

import { LogOut } from "lucide-react";
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
    <div className="flex items-center gap-3">
      <span className="hidden text-sm text-muted-foreground sm:inline">{user?.nickname}</span>
      <Button type="button" variant="outline" size="sm" disabled={pending} onClick={handleLogout}>
        <LogOut aria-hidden="true" />
        {pending ? "正在退出" : "退出登录"}
      </Button>
    </div>
  );
}
