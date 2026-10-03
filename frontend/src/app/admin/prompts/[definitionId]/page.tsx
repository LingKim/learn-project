import { PromptDetailPage } from "@/features/prompt-management/prompt-detail-page";

export default async function Page({ params }: { params: Promise<{ definitionId: string }> }) {
  const { definitionId } = await params;
  return <PromptDetailPage definitionId={definitionId} />;
}
