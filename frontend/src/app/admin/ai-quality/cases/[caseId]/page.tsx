import { QualityAdminDetailPage } from "@/features/ai-quality/admin-pages";

export default async function Page({ params }: { params: Promise<{ caseId: string }> }) {
  const { caseId } = await params;
  return <QualityAdminDetailPage id={caseId} />;
}
