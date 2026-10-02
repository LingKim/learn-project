import { describe, expect, it } from "vitest";
import type { ProcessingTaskView } from "./api";
import { processingDescription } from "./processing-status";
import { fileManagementKeys, processingTaskQueryOptions } from "./queries";

const task: ProcessingTaskView = {
  id: "task",
  status: "processing",
  stage: "extracting",
  completed_units: null,
  total_units: null,
  attempt_count: 1,
  last_error_code: null,
  retryable: false,
  created_at: "2026-10-02T00:00:00Z",
  requires_ai_consent: false,
  active_version: null,
};

describe("document processing presentation", () => {
  it("uses the real stage with no invented percentage", () => {
    expect(processingDescription(task)).toBe("提取正文");
    expect(
      processingDescription({ ...task, stage: "ocr", completed_units: 2, total_units: 5 }),
    ).toBe("识别扫描页 2 / 5");
  });
  it("shows consent before model execution and preserves old version after failure", () => {
    expect(processingDescription({ ...task, status: "pending", requires_ai_consent: true })).toBe(
      "等待确认 AI 资料处理说明",
    );
    expect(
      processingDescription({
        ...task,
        status: "failed",
        last_error_code: "DOCUMENT_OCR_NO_TEXT",
        active_version: {
          id: "version",
          version_number: 1,
          chunk_count: 3,
          image_count: 0,
          unrecognized_image_count: 0,
          native_page_count: 0,
          ocr_page_count: 0,
        },
      }),
    ).toContain("旧版本仍可检索");
  });
  it("does not assume the original file is unclear when a quality check rejects OCR", () => {
    expect(
      processingDescription({
        ...task,
        status: "failed",
        last_error_code: "DOCUMENT_OCR_LOW_CONFIDENCE",
      }),
    ).toBe("识别文字未通过质量检查，请重试解析");
  });
  it("does not show an upstream error response containing internals", () => {
    expect(
      processingDescription({
        ...task,
        status: "failed",
        last_error_code: "SYNTHETIC_SECRET_INTERNAL",
      }),
    ).not.toContain("SYNTHETIC_SECRET");
  });
  it("separates per-file task queries by ownership scope", () => {
    expect(processingTaskQueryOptions("kb-a", "file-a").queryKey).toEqual(
      fileManagementKeys.processing("kb-a", "file-a"),
    );
    expect(processingTaskQueryOptions("kb-a", "file-a").queryKey).not.toEqual(
      processingTaskQueryOptions("kb-b", "file-a").queryKey,
    );
  });
});
