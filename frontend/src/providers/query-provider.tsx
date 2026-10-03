"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { useAuth } from "@/features/auth/auth-provider";
import { createAppQueryClient } from "@/lib/query/client";

export function QueryProvider({ children }: Readonly<{ children: React.ReactNode }>) {
  const { status, user } = useAuth();
  // 业务 Query key 不含账号；切换会话必须连同页面状态一起更换缓存，避免复用上一位用户的私有结果。
  return (
    <SessionQueryProvider key={JSON.stringify([status, user?.id ?? null])}>
      {children}
    </SessionQueryProvider>
  );
}

function SessionQueryProvider({ children }: Readonly<{ children: React.ReactNode }>) {
  const [queryClient] = useState(createAppQueryClient);
  useEffect(() => {
    // 旧会话取消未完成查询并清除缓存；迟到 mutation 也只持有已退出会话的旧 client。
    return () => queryClient.clear();
  }, [queryClient]);

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
