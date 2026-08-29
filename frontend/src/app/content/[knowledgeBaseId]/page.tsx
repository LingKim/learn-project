import { ProtectedRoute } from "@/features/auth/auth-route";
import { KnowledgeBaseDetail } from "@/features/file-management/knowledge-base-detail";

export default async function KnowledgeBaseDetailPage({
  params,
}: {
  params: Promise<{ knowledgeBaseId: string }>;
}) {
  const { knowledgeBaseId } = await params;
  return (
    <ProtectedRoute>
      <KnowledgeBaseDetail knowledgeBaseId={knowledgeBaseId} />
    </ProtectedRoute>
  );
}
