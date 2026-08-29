import { describe, expect, it } from "vitest";

import {
  fileManagementKeys,
  knowledgeBaseListQueryOptions,
  knowledgeFileListQueryOptions,
} from "./queries";

describe("file management query keys", () => {
  it("keeps pagination and filters in stable resource keys", () => {
    expect(knowledgeBaseListQueryOptions(2, 10).queryKey).toEqual([
      "file-management",
      "knowledge-bases",
      "list",
      2,
      10,
    ]);
    expect(
      knowledgeFileListQueryOptions("base-1", 3, 20, "事务", "pending_processing").queryKey,
    ).toEqual([
      "file-management",
      "knowledge-bases",
      "base-1",
      "files",
      "list",
      3,
      20,
      "事务",
      "pending_processing",
    ]);
    expect(fileManagementKeys.files("base-1")).toEqual([
      "file-management",
      "knowledge-bases",
      "base-1",
      "files",
    ]);
  });
});
