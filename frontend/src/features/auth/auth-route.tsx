"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, type ReactNode } from "react";

import { useAuth } from "./auth-provider";

function LoadingScreen() {
  return (
    <main className="grid min-h-dvh place-items-center bg-background" aria-busy="true">
      <p className="text-sm text-muted-foreground">正在恢复登录状态…</p>
    </main>
  );
}

export function ProtectedRoute({ children }: Readonly<{ children: ReactNode }>) {
  const router = useRouter();
  const { status } = useAuth();

  useEffect(() => {
    if (status === "anonymous") router.replace("/login");
  }, [router, status]);

  if (status !== "authenticated") return <LoadingScreen />;
  return children;
}

export function AdminRoute({ children }: Readonly<{ children: ReactNode }>) {
  const { status, user } = useAuth();
  return (
    <ProtectedRoute>
      {status === "authenticated" && user?.role === "admin" ? (
        children
      ) : (
        <main className="grid min-h-dvh place-items-center bg-background p-6">
          <div className="max-w-md text-center">
            <h1 className="text-xl font-bold">无权访问管理功能</h1>
            <p className="mt-3 text-sm text-muted-foreground">该功能仅供系统管理员使用。</p>
            <Link
              href="/learning"
              className="mt-5 inline-flex rounded-[7px] border bg-primary px-4 py-2 text-sm"
            >
              返回学习室
            </Link>
          </div>
        </main>
      )}
    </ProtectedRoute>
  );
}

export function PublicAuthRoute({ children }: Readonly<{ children: ReactNode }>) {
  const router = useRouter();
  const { status } = useAuth();

  useEffect(() => {
    if (status === "authenticated") router.replace("/");
  }, [router, status]);

  if (status !== "anonymous") return <LoadingScreen />;
  return children;
}
