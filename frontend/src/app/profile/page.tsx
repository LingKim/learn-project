import { ProtectedRoute } from "@/features/auth/auth-route";
import { UserProfilePage } from "@/features/user-profile/profile-page";

export default function ProfilePage() {
  return (
    <ProtectedRoute>
      <UserProfilePage />
    </ProtectedRoute>
  );
}
