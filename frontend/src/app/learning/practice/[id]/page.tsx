import { ProtectedRoute } from "@/features/auth/auth-route";
import { PracticePage } from "@/features/practice/practice-page";
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ attempt?: string; view?: string; request?: string; run?: string }>;
}) {
  const [{ id }, query] = await Promise.all([params, searchParams]);
  return (
    <ProtectedRoute>
      <PracticePage
        key={`${id}:${query.attempt ?? ""}:${query.view ?? ""}`}
        setId={id}
        attemptId={query.attempt}
        report={query.view === "report"}
        requestKey={query.request}
        runId={query.run}
      />
    </ProtectedRoute>
  );
}
