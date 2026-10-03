import type { ReactNode } from "react";
import { AdminShell } from "@/components/admin-shell";
import { AdminRoute } from "@/features/auth/auth-route";
import { PromptDraftScope } from "@/features/prompt-management/draft-memory";

export default function AdminLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <AdminRoute>
      <PromptDraftScope>
        <AdminShell>{children}</AdminShell>
      </PromptDraftScope>
    </AdminRoute>
  );
}
