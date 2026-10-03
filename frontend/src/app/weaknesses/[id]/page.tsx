import { ProtectedRoute } from "@/features/auth/auth-route";
import { WeaknessPage } from "@/features/learning-assets/weakness-page";
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <ProtectedRoute>
      <WeaknessPage key={id} id={id} />
    </ProtectedRoute>
  );
}
