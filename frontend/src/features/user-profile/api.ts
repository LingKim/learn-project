import { authenticatedAccessToken } from "@/features/auth/auth-provider";
import {
  avatarUploadSessionsComplete,
  avatarUploadSessionsCreate,
  userAvatarDelete,
  userAvatarGet,
  userProfileGet,
  userProfileUpdate,
} from "@/lib/api/generated/sdk.gen";
import type {
  AvatarDeleteRequest,
  AvatarUploadCompleteView,
  AvatarUploadCreate,
  AvatarUploadPlan,
  UserProfilePatch,
  UserProfileView,
} from "@/lib/api/generated/types.gen";
import { ApiError, toApiError } from "@/lib/api/errors";
import {
  API_BASE_URL,
  requestMutation,
  requestQueryData,
  type MutationResult,
} from "@/lib/api/protocol";
import { putPresignedObject } from "@/lib/api/upload-transport";

const sharedOptions = {
  baseUrl: API_BASE_URL,
  credentials: "include" as const,
  throwOnError: true as const,
};

async function authorizedOptions() {
  const accessToken = await authenticatedAccessToken();
  return { ...sharedOptions, headers: { Authorization: `Bearer ${accessToken}` } };
}

export type {
  AvatarUploadCompleteView,
  AvatarUploadCreate,
  AvatarUploadPlan,
  UserProfilePatch,
  UserProfileView,
};

export async function getUserProfile(): Promise<UserProfileView> {
  const options = await authorizedOptions();
  return requestQueryData(() => userProfileGet(options));
}

export async function updateUserProfile(
  body: UserProfilePatch,
): Promise<MutationResult<UserProfileView>> {
  const options = await authorizedOptions();
  return requestMutation(() => userProfileUpdate({ ...options, body }));
}

export async function createAvatarUpload(
  body: AvatarUploadCreate,
  idempotencyKey: string,
): Promise<MutationResult<AvatarUploadPlan>> {
  const options = await authorizedOptions();
  return requestMutation(() =>
    avatarUploadSessionsCreate({
      ...options,
      headers: { ...options.headers, "Idempotency-Key": idempotencyKey },
      body,
    }),
  );
}

export async function completeAvatarUpload(
  uploadId: string,
): Promise<MutationResult<AvatarUploadCompleteView>> {
  const options = await authorizedOptions();
  return requestMutation(() =>
    avatarUploadSessionsComplete({ ...options, path: { upload_id: uploadId } }),
  );
}

export async function deleteUserAvatar(
  body: AvatarDeleteRequest,
): Promise<MutationResult<UserProfileView>> {
  const options = await authorizedOptions();
  return requestMutation(() => userAvatarDelete({ ...options, body }));
}

export async function getUserAvatar(): Promise<Blob> {
  const options = await authorizedOptions();
  try {
    const result = await userAvatarGet({ ...options, parseAs: "blob" });
    if (!(result.data instanceof Blob)) {
      throw new ApiError("头像响应格式不正确", { errorKey: "AVATAR_RESPONSE_INVALID" });
    }
    return result.data;
  } catch (error) {
    throw toApiError(error);
  }
}

export { putPresignedObject };
