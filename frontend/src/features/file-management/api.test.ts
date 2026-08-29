import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  fileUploadSessionsCreate,
  knowledgeBaseFilesList,
  knowledgeBasesList,
} from "@/lib/api/generated/sdk.gen";
import { authenticatedAccessToken } from "@/features/auth/auth-provider";

import { createUploadSession, listKnowledgeBases, listKnowledgeFiles } from "./api";

vi.mock("@/features/auth/auth-provider", () => ({
  authenticatedAccessToken: vi.fn(),
}));

vi.mock("@/lib/api/generated/sdk.gen", () => ({
  fileUploadSessionsCreate: vi.fn(),
  knowledgeBaseFilesList: vi.fn(),
  knowledgeBasesList: vi.fn(),
}));

const response = new Response(null, { status: 200 });

describe("file management api", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(authenticatedAccessToken).mockResolvedValue("access-token");
  });

  it("loads knowledge bases through the generated SDK and shared page protocol", async () => {
    vi.mocked(knowledgeBasesList).mockResolvedValue({
      data: {
        code: 200,
        message: "success",
        data: [],
        meta: { page: 2, page_size: 10, total: 0, total_pages: 0 },
      },
      error: undefined,
      request: new Request("http://localhost/api/v1/knowledge-bases"),
      response,
    });

    await expect(listKnowledgeBases({ page: 2, pageSize: 10 })).resolves.toEqual({
      data: [],
      meta: { page: 2, page_size: 10, total: 0, total_pages: 0 },
    });
    expect(knowledgeBasesList).toHaveBeenCalledWith(
      expect.objectContaining({
        baseUrl: "/api/backend",
        headers: { Authorization: "Bearer access-token" },
        query: { page: 2, page_size: 10 },
      }),
    );
  });

  it("keeps file filters in the feature API", async () => {
    vi.mocked(knowledgeBaseFilesList).mockResolvedValue({
      data: {
        code: 200,
        message: "success",
        data: [],
        meta: { page: 1, page_size: 20, total: 0, total_pages: 0 },
      },
      error: undefined,
      request: new Request("http://localhost/api/v1/files"),
      response,
    });

    await listKnowledgeFiles({
      knowledgeBaseId: "base-1",
      search: "事务",
      status: "pending_processing",
    });

    expect(knowledgeBaseFilesList).toHaveBeenCalledWith(
      expect.objectContaining({
        path: { knowledge_base_id: "base-1" },
        query: {
          page: 1,
          page_size: 20,
          search: "事务",
          status: "pending_processing",
        },
      }),
    );
  });

  it("sends the upload idempotency key without exposing it to components", async () => {
    vi.mocked(fileUploadSessionsCreate).mockResolvedValue({
      data: {
        code: 200,
        message: "上传会话已创建",
        data: {
          session_id: "session-1",
          status: "uploading",
          upload_mode: "single",
          expires_at: "2026-08-29T12:00:00Z",
          upload_url: "http://storage/upload",
          parts: [],
        },
      },
      error: undefined,
      request: new Request("http://localhost/api/v1/uploads"),
      response,
    });

    await createUploadSession(
      "base-1",
      { filename: "notes.txt", size: 5, declared_mime: "text/plain" },
      "idem-1",
    );

    expect(fileUploadSessionsCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        headers: {
          Authorization: "Bearer access-token",
          "Idempotency-Key": "idem-1",
        },
      }),
    );
  });
});
