import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CardSources } from "./card-sources";
import { syntheticCard } from "./fixtures.test-support";
import { getExplanationSource } from "./api";
import { learningAssetKeys } from "./queries";
import { ApiError } from "@/lib/api/errors";
vi.mock("./api", () => ({ getExplanationSource: vi.fn() }));
afterEach(cleanup);
it("资料来源失效后立刻隐藏预览并移除原文cache，已保存卡片仍保留", async () => {
  const source = {
    source_id: "source-1",
    file_id: "file-1",
    file_asset_id: "asset-1",
    processing_version_id: "processing-1",
    chunk_id: "chunk-1",
    display_name: "合成资料",
    page_start: 1,
  };
  vi.mocked(getExplanationSource).mockResolvedValue({
    source,
    available: true,
    evidence: "合成受保护原文",
  });
  const card = { ...syntheticCard, source_mode: "materials" as const, citations: [source] };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { rerender } = render(
    <QueryClientProvider client={client}>
      <CardSources card={card} sourceAvailable />
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "合成资料 · 第 1 页" }));
  await waitFor(() => expect(screen.getByText("合成受保护原文")).toBeVisible());
  expect(
    client.getQueryData(
      learningAssetKeys.source(card.explanation_id, card.version, source.source_id),
    ),
  ).toBeDefined();
  rerender(
    <QueryClientProvider client={client}>
      <CardSources card={card} sourceAvailable={false} />
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.queryByText("合成受保护原文")).not.toBeInTheDocument());
  expect(
    client.getQueryData(
      learningAssetKeys.source(card.explanation_id, card.version, source.source_id),
    ),
  ).toBeUndefined();
  expect(screen.getByRole("button", { name: "来源已失效" })).toBeDisabled();
});
it("预览接口发现404时也清除上次成功缓存，不等待父详情刷新", async () => {
  const source = {
    source_id: "source-2",
    file_id: "file-2",
    file_asset_id: "asset-2",
    processing_version_id: "processing-2",
    chunk_id: "chunk-2",
    display_name: "已删除合成资料",
  };
  vi.mocked(getExplanationSource).mockRejectedValue(
    new ApiError("来源已失效", { status: 404, errorKey: "LEARNING_ASSET_NOT_FOUND" }),
  );
  const card = { ...syntheticCard, source_mode: "materials" as const, citations: [source] };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const key = learningAssetKeys.source(card.explanation_id, card.version, source.source_id);
  client.setQueryData(key, { source, available: true, evidence: "上次成功的合成原文" });
  render(
    <QueryClientProvider client={client}>
      <CardSources card={card} sourceAvailable />
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: source.display_name }));
  await waitFor(() => expect(screen.queryByText("上次成功的合成原文")).not.toBeInTheDocument());
  await waitFor(() => expect(client.getQueryData(key)).toBeUndefined());
  expect(screen.getByRole("alert")).toHaveTextContent("来源已失效");
});
