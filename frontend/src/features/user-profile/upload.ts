import { ApiError } from "@/lib/api/errors";

import {
  completeAvatarUpload,
  createAvatarUpload,
  putPresignedObject,
  type AvatarUploadCompleteView,
} from "./api";

const ACCEPTED_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const MAX_AVATAR_BYTES = 5 * 1024 * 1024;

export type UploadAvatarInput = { file: File; profileVersion: number };

export function validateAvatarFile(file: File): void {
  if (!ACCEPTED_TYPES.has(file.type)) {
    throw new ApiError("请选择 JPEG、PNG 或 WebP 图片", { errorKey: "AVATAR_TYPE_INVALID" });
  }
  if (file.size > MAX_AVATAR_BYTES) {
    throw new ApiError("头像不能超过 5 MB", { errorKey: "AVATAR_TOO_LARGE" });
  }
  if (file.size === 0) {
    throw new ApiError("头像文件不能为空", { errorKey: "AVATAR_EMPTY" });
  }
}

function idempotencyKey(): string {
  return typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `avatar-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export async function uploadAvatar({
  file,
  profileVersion,
}: UploadAvatarInput): Promise<AvatarUploadCompleteView> {
  validateAvatarFile(file);
  const session = await createAvatarUpload(
    {
      filename: file.name,
      size: file.size,
      declared_mime: file.type as "image/jpeg" | "image/png" | "image/webp",
      profile_version: profileVersion,
    },
    idempotencyKey(),
  );
  await putPresignedObject(session.data.upload_url, file, file.type);

  const deadline = Date.now() + 60_000;
  let result = (await completeAvatarUpload(session.data.id)).data;
  while (!new Set(["completed", "failed"]).has(result.status) && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 750));
    result = (await completeAvatarUpload(session.data.id)).data;
  }
  if (result.status === "completed") return result;
  if (result.status === "failed") {
    throw new ApiError("头像处理失败，原头像已保留", {
      errorKey: result.failure_code ?? "AVATAR_PROCESSING_FAILED",
    });
  }
  throw new ApiError("头像仍在处理中，请稍后重试", { errorKey: "AVATAR_PROCESSING_TIMEOUT" });
}
