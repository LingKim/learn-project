import type { Metadata } from "next";

import { LoginForm } from "@/features/auth/auth-forms";
import { AuthShell } from "@/features/auth/auth-shell";

export const metadata: Metadata = {
  title: "登录 · 学面通AI",
  description: "登录学面通AI，继续学习与面试准备。",
};

export default function LoginPage() {
  return (
    <AuthShell
      eyebrow="专注学习与面试"
      title="把复杂知识，学得更清楚。"
      description="专注学习、面试准备与知识沉淀，让每一次提问都有持续的价值。"
    >
      <LoginForm />
    </AuthShell>
  );
}
