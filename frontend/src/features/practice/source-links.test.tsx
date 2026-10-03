import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { getPracticeSource } from "./api";
import { singleQuestion } from "./fixtures.test-support";
import { practiceSourceOptions } from "./queries";
import { SourceLinks } from "./source-links";
vi.mock("./api", () => ({ getPracticeSource: vi.fn() }));
afterEach(cleanup);
it("来源接口发现404时移除先前原文缓存，无须等待题集详情刷新", async () => {
  const source = {
    source_id: "source",
    display_name: "合成来源",
    file_id: "file",
    file_asset_id: "asset",
    processing_version_id: "version",
    chunk_id: "chunk",
  };
  const question = { ...singleQuestion, source_refs: [source] };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const key = practiceSourceOptions(
    "set",
    "revision",
    question.question_id,
    source.source_id,
  ).queryKey;
  client.setQueryData(key, { source, available: true, evidence: "旧来源正文" });
  vi.mocked(getPracticeSource).mockRejectedValue(new ApiError("来源已失效", { status: 404 }));
  render(
    <QueryClientProvider client={client}>
      <SourceLinks setId="set" revisionId="revision" question={question} available />
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: source.display_name }));
  await waitFor(() => expect(getPracticeSource).toHaveBeenCalled());
  await waitFor(() => expect(client.getQueryData(key)).toBeUndefined());
  expect(screen.queryByText("旧来源正文")).not.toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("来源已失效");
});
