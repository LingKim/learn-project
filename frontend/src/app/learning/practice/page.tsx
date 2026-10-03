import { ProtectedRoute } from "@/features/auth/auth-route";
import { PracticePage } from "@/features/practice/practice-page";
import { TargetPracticePage } from "@/features/practice/target-practice-page";

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const text = (value: string | string[] | undefined) => (typeof value === "string" ? value : "");
  const weaknessId = text(params.weakness);
  const explanationId = text(params.explanation);
  return (
    <ProtectedRoute>
      {weaknessId || explanationId ? (
        <TargetPracticePage
          weaknessId={weaknessId}
          explanationId={explanationId}
          version={Number(text(weaknessId ? params.version : params.card))}
        />
      ) : (
        <PracticePage />
      )}
    </ProtectedRoute>
  );
}
