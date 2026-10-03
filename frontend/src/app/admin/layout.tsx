import type { ReactNode } from "react";
import { AdminShell } from "@/components/admin-shell";
import { AdminRoute } from "@/features/auth/auth-route";

export default function AdminLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <AdminRoute>
      <AdminShell>{children}</AdminShell>
    </AdminRoute>
  );
}
