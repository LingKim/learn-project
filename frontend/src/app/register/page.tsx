import type { Metadata } from "next";

import { RegisterForm } from "@/features/auth/auth-forms";
import { PublicAuthRoute } from "@/features/auth/auth-route";
import { AuthShell } from "@/features/auth/auth-shell";

export const metadata: Metadata = {
  title: "注册 · 学面通AI",
  description: "创建学面通AI账号。",
};

export default function RegisterPage() {
  return (
    <PublicAuthRoute>
      <AuthShell
        variant="register"
        eyebrow="建立个人知识系统"
        title="从今天开始，建立自己的知识系统。"
        description="学习室、面试间、笔记本与计划，一起连接你的全部成长轨迹。"
      >
        <RegisterForm />
      </AuthShell>
    </PublicAuthRoute>
  );
}
