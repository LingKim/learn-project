import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  cancelUploadSession,
  completeUploadSession,
  createUploadSession,
  getUploadSession,
  putPresignedFile,
  signUploadParts,
} from "./api";
import { uploadKnowledgeFile } from "./upload";

vi.mock("./api", () => ({
  cancelUploadSession: vi.fn(),
  completeUploadSession: vi.fn(),
  createUploadSession: vi.fn(),
  getUploadSession: vi.fn(),
  putPresignedFile: vi.fn(),
  signUploadParts: vi.fn(),
}));

const completedSession = {
  session_id: "session-1",
  status: "completed",
  upload_mode: "single",
  filename: "notes.txt",
  size: 5,
  expires_at: "2026-08-29T12:00:00Z",
  knowledge_file_id: "file-1",
};

describe("uploadKnowledgeFile", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getUploadSession).mockResolvedValue(completedSession);
    vi.mocked(completeUploadSession).mockResolvedValue({
      data: { ...completedSession, status: "verifying" },
      message: "文件已提交校验",
    });
    vi.mocked(cancelUploadSession).mockResolvedValue({
      data: { ...completedSession, status: "cancelled" },
      message: "上传会话已取消",
    });
  });

  it("uploads a single file and waits for server verification", async () => {
    vi.mocked(createUploadSession).mockResolvedValue({
      data: {
        session_id: "session-1",
        status: "uploading",
        upload_mode: "single",
        expires_at: "2026-08-29T12:00:00Z",
        upload_url: "http://storage/upload",
        parts: [],
      },
      message: "上传会话已创建",
    });
    vi.mocked(putPresignedFile).mockResolvedValue(new Response(null, { status: 200 }));
    const file = new File(["hello"], "notes.txt", { type: "text/plain" });

    await expect(uploadKnowledgeFile({ knowledgeBaseId: "base-1", file })).resolves.toEqual({
      data: completedSession,
      message: "文件已上传·待解析",
    });
    expect(putPresignedFile).toHaveBeenCalledWith("http://storage/upload", file, "text/plain");
    expect(completeUploadSession).toHaveBeenCalledWith("session-1", { parts: [] });
  });

  it("signs, uploads and completes multipart chunks", async () => {
    vi.mocked(createUploadSession).mockResolvedValue({
      data: {
        session_id: "session-1",
        status: "uploading",
        upload_mode: "multipart",
        expires_at: "2026-08-29T12:00:00Z",
        part_size: 3,
        parts: [],
      },
      message: "上传会话已创建",
    });
    vi.mocked(signUploadParts).mockResolvedValue({
      data: [
        { part_number: 1, upload_url: "http://storage/part-1" },
        { part_number: 2, upload_url: "http://storage/part-2" },
      ],
      message: "success",
    });
    vi.mocked(putPresignedFile)
      .mockResolvedValueOnce(new Response(null, { status: 200, headers: { ETag: '"etag-1"' } }))
      .mockResolvedValueOnce(new Response(null, { status: 200, headers: { ETag: '"etag-2"' } }));
    const file = new File(["abcdef"], "notes.txt", { type: "text/plain" });

    await uploadKnowledgeFile({ knowledgeBaseId: "base-1", file });

    expect(signUploadParts).toHaveBeenCalledWith("session-1", { part_numbers: [1, 2] });
    expect(completeUploadSession).toHaveBeenCalledWith("session-1", {
      parts: [
        { part_number: 1, etag: '"etag-1"' },
        { part_number: 2, etag: '"etag-2"' },
      ],
    });
  });

  it("cancels the upload session when object storage upload fails", async () => {
    vi.mocked(createUploadSession).mockResolvedValue({
      data: {
        session_id: "session-1",
        status: "uploading",
        upload_mode: "single",
        expires_at: "2026-08-29T12:00:00Z",
        upload_url: "http://storage/upload",
        parts: [],
      },
      message: "上传会话已创建",
    });
    vi.mocked(putPresignedFile).mockRejectedValue(new Error("storage unavailable"));
    const file = new File(["hello"], "notes.txt", { type: "text/plain" });

    await expect(uploadKnowledgeFile({ knowledgeBaseId: "base-1", file })).rejects.toThrow(
      "storage unavailable",
    );
    expect(cancelUploadSession).toHaveBeenCalledWith("session-1");
  });
});
