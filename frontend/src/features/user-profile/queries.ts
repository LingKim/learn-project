import { mutationOptions, queryOptions, type QueryClient } from "@tanstack/react-query";

import {
  deleteUserAvatar,
  getUserAvatar,
  getUserProfile,
  updateUserProfile,
  type UserProfilePatch,
} from "./api";
import { uploadAvatar, type UploadAvatarInput } from "./upload";

export const userProfileKeys = {
  all: ["user-profile"] as const,
  detail: () => [...userProfileKeys.all, "detail"] as const,
  avatar: (version: number) => [...userProfileKeys.all, "avatar", version] as const,
};

export function userProfileQueryOptions() {
  return queryOptions({ queryKey: userProfileKeys.detail(), queryFn: getUserProfile });
}

export function userAvatarQueryOptions(version: number, enabled: boolean) {
  return queryOptions({
    queryKey: userProfileKeys.avatar(version),
    queryFn: getUserAvatar,
    enabled,
    staleTime: Number.POSITIVE_INFINITY,
  });
}

export function updateUserProfileMutationOptions(queryClient: QueryClient) {
  return mutationOptions({
    mutationKey: [...userProfileKeys.all, "update"],
    mutationFn: (body: UserProfilePatch) => updateUserProfile(body),
    onSuccess: (result) => queryClient.setQueryData(userProfileKeys.detail(), result.data),
    meta: { errorMode: "local" },
  });
}

export function uploadAvatarMutationOptions(queryClient: QueryClient) {
  return mutationOptions({
    mutationKey: [...userProfileKeys.all, "avatar", "upload"],
    mutationFn: (input: UploadAvatarInput) => uploadAvatar(input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: userProfileKeys.all }),
    meta: { errorMode: "local" },
  });
}

export function deleteAvatarMutationOptions(queryClient: QueryClient) {
  return mutationOptions({
    mutationKey: [...userProfileKeys.all, "avatar", "delete"],
    mutationFn: (version: number) => deleteUserAvatar({ version }),
    onSuccess: (result) => {
      queryClient.removeQueries({ queryKey: [...userProfileKeys.all, "avatar"] });
      queryClient.setQueryData(userProfileKeys.detail(), result.data);
    },
    meta: { errorMode: "local" },
  });
}
