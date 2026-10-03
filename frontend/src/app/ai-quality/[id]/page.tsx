import { ProtectedRoute } from "@/features/auth/auth-route";
import { MyQualityCasePage } from "@/features/ai-quality/user-pages";
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <ProtectedRoute>
      <MyQualityCasePage key={id} id={id} />
    </ProtectedRoute>
  );
}
