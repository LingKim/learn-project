import { ProtectedRoute } from "@/features/auth/auth-route";
import { ExplanationPage } from "@/features/learning-assets/explanation-page";
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ weakness?: string; version?: string }>;
}) {
  const params = await searchParams;
  const version = Number(params.version);
  return (
    <ProtectedRoute>
      <ExplanationPage
        key={params.weakness ?? "direct"}
        weaknessId={params.weakness}
        weaknessVersion={Number.isInteger(version) && version > 0 ? version : undefined}
      />
    </ProtectedRoute>
  );
}
