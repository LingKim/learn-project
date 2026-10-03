import { ProtectedRoute } from "@/features/auth/auth-route";
import { PracticePage } from "@/features/practice/practice-page";
export default function Page() {
  return (
    <ProtectedRoute>
      <PracticePage />
    </ProtectedRoute>
  );
}
