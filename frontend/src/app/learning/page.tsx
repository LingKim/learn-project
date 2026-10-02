import { ProtectedRoute } from "@/features/auth/auth-route";
import { LearningPage } from "@/features/learning/learning-page";
export default function Page() {
  return (
    <ProtectedRoute>
      <LearningPage />
    </ProtectedRoute>
  );
}
