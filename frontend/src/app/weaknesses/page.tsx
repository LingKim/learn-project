import { ProtectedRoute } from "@/features/auth/auth-route";
import { WeaknessesPage } from "@/features/learning-assets/weaknesses-page";
export default function Page() {
  return (
    <ProtectedRoute>
      <WeaknessesPage />
    </ProtectedRoute>
  );
}
