import { ProtectedRoute } from "@/features/auth/auth-route";
import { MyQualityCasesPage } from "@/features/ai-quality/user-pages";
export default function Page() {
  return (
    <ProtectedRoute>
      <MyQualityCasesPage />
    </ProtectedRoute>
  );
}
