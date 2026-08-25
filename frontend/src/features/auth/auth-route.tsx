"use client";

import { useRouter } from "next/navigation";
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

export function PublicAuthRoute({ children }: Readonly<{ children: ReactNode }>) {
  const router = useRouter();
  const { status } = useAuth();

  useEffect(() => {
    if (status === "authenticated") router.replace("/");
  }, [router, status]);

  if (status !== "anonymous") return <LoadingScreen />;
  return children;
}
