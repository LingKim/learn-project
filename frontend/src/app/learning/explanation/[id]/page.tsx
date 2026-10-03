import { ProtectedRoute } from "@/features/auth/auth-route";
import { ExplanationDetailPage } from "@/features/learning-assets/explanation-detail-page";
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ run?: string }>;
}) {
  const [{ id }, query] = await Promise.all([params, searchParams]);
  return (
    <ProtectedRoute>
      <ExplanationDetailPage key={`${id}:${query.run ?? ""}`} id={id} runId={query.run} />
    </ProtectedRoute>
  );
}
