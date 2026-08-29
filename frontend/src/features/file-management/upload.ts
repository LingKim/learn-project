import { ApiError } from "@/lib/api/errors";
import type { MutationResult } from "@/lib/api/protocol";

import {
  cancelUploadSession,
  completeUploadSession,
  createUploadSession,
  getUploadSession,
  putPresignedFile,
  signUploadParts,
  type UploadSessionView,
} from "./api";

const SIGN_BATCH_SIZE = 100;
const TERMINAL_UPLOAD_STATUSES = new Set(["completed", "failed", "cancelled", "expired"]);

export type UploadKnowledgeFileInput = {
  knowledgeBaseId: string;
  file: File;
};

function createIdempotencyKey(): string {
  return typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `upload-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

async function uploadMultipart(
  sessionId: string,
  file: File,
  partSize: number,
): Promise<Array<{ part_number: number; etag: string }>> {
  const partCount = Math.ceil(file.size / partSize);
  const completedParts: Array<{ part_number: number; etag: string }> = [];

  for (let batchStart = 1; batchStart <= partCount; batchStart += SIGN_BATCH_SIZE) {
    const partNumbers = Array.from(
      { length: Math.min(SIGN_BATCH_SIZE, partCount - batchStart + 1) },
      (_, index) => batchStart + index,
    );
    const signedParts = (await signUploadParts(sessionId, { part_numbers: partNumbers })).data;
    for (const signedPart of signedParts) {
      const start = (signedPart.part_number - 1) * partSize;
      const response = await putPresignedFile(
        signedPart.upload_url,
        file.slice(start, start + partSize),
      );
      const etag = response.headers.get("etag");
      if (!etag) {
        throw new ApiError("对象存储未返回分片 ETag", {
          errorKey: "OBJECT_STORAGE_ETAG_MISSING",
        });
      }
      completedParts.push({ part_number: signedPart.part_number, etag });
    }
  }
  return completedParts;
}

async function waitForUploadCompletion(sessionId: string): Promise<UploadSessionView> {
  const deadline = Date.now() + 60_000;
  let current = await getUploadSession(sessionId);
  while (!TERMINAL_UPLOAD_STATUSES.has(current.status) && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 750));
    current = await getUploadSession(sessionId);
  }
  if (current.status === "completed") return current;
  if (current.status === "failed") {
    throw new ApiError("文件校验失败", {
      errorKey: current.failure_code ?? "FILE_VALIDATION_FAILED",
    });
  }
  if (!TERMINAL_UPLOAD_STATUSES.has(current.status)) {
    throw new ApiError("文件仍在校验中，请稍后刷新列表", {
      errorKey: "FILE_VALIDATION_TIMEOUT",
    });
  }
  throw new ApiError("上传会话未完成", { errorKey: "FILE_UPLOAD_NOT_COMPLETED" });
}

export async function uploadKnowledgeFile({
  knowledgeBaseId,
  file,
}: UploadKnowledgeFileInput): Promise<MutationResult<UploadSessionView>> {
  const session = await createUploadSession(
    knowledgeBaseId,
    {
      filename: file.name,
      size: file.size,
      declared_mime: file.type || null,
    },
    createIdempotencyKey(),
  );
  const plan = session.data;

  if (plan.upload_mode === "reuse") {
    throw new ApiError("检测到重复文件，请先选择关联、移动或取消", {
      status: 409,
      code: 409,
      errorKey: "DUPLICATE_ACTION_REQUIRED",
    });
  }

  try {
    if (plan.upload_mode === "single") {
      if (!plan.upload_url) throw new ApiError("上传地址缺失", { errorKey: "UPLOAD_PLAN_INVALID" });
      await putPresignedFile(plan.upload_url, file, file.type || undefined);
      await completeUploadSession(plan.session_id, { parts: [] });
    } else {
      if (!plan.part_size) throw new ApiError("分片大小缺失", { errorKey: "UPLOAD_PLAN_INVALID" });
      const parts = await uploadMultipart(plan.session_id, file, plan.part_size);
      await completeUploadSession(plan.session_id, { parts });
    }
    return {
      data: await waitForUploadCompletion(plan.session_id),
      message: "文件已上传·待解析",
    };
  } catch (error) {
    await cancelUploadSession(plan.session_id).catch(() => undefined);
    throw error;
  }
}
