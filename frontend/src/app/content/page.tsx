import { ProtectedRoute } from "@/features/auth/auth-route";
import { KnowledgeBaseOverview } from "@/features/file-management/knowledge-base-overview";

export default function ContentPage() {
  return (
    <ProtectedRoute>
      <KnowledgeBaseOverview />
    </ProtectedRoute>
  );
}
