import type { Metadata } from "next";

import { ForcedPasswordChangeForm } from "@/features/auth/auth-forms";
import { AuthShell } from "@/features/auth/auth-shell";

export const metadata: Metadata = {
  title: "修改临时密码 · 学面通AI",
  description: "首次登录时修改临时密码。",
};

export default function FirstLoginChangePasswordPage() {
  return (
    <AuthShell
      compact
      eyebrow="账号安全"
      title="先设置自己的密码，再继续学习。"
      description="临时密码只负责把账号安全地交到你手里，新的密码由你掌握。"
    >
      <ForcedPasswordChangeForm />
    </AuthShell>
  );
}
