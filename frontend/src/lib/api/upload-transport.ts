import { ApiError, toApiError } from "./errors";

export async function putPresignedObject(
  url: string,
  body: Blob,
  contentType?: string,
): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: "PUT",
      body,
      headers: contentType ? { "Content-Type": contentType } : undefined,
    });
  } catch (error) {
    throw toApiError(error);
  }
  if (!response.ok) {
    throw new ApiError(`对象存储上传失败（${response.status}）`, {
      status: response.status,
      code: response.status,
      errorKey: "OBJECT_STORAGE_UPLOAD_FAILED",
    });
  }
  return response;
}
