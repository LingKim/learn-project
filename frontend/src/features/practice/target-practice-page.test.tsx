import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { TargetPracticePage } from "./target-practice-page";

const state = vi.hoisted(() => ({ weakness: null as unknown, card: null as unknown }));
vi.mock("@/features/learning-assets/queries", () => ({
  weaknessOptions: (id: string) => ({ queryKey: ["weakness", id], queryFn: () => state.weakness }),
  explanationCardOptions: (id: string, version: number) => ({
    queryKey: ["card", id, version],
    queryFn: () => state.card,
  }),
}));
vi.mock("@/features/file-management/content-shell", () => ({
  ContentShell: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("./practice-page", () => ({
  PracticePage: ({ initialConfig }: { initialConfig: unknown }) => (
    <pre data-testid="practice-config">{JSON.stringify(initialConfig)}</pre>
  ),
}));
afterEach(cleanup);
function view(props: Parameters<typeof TargetPracticePage>[0]) {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <TargetPracticePage {...props} />
    </QueryClientProvider>,
  );
}
it("uses the selected card version's immutable topic and complete source scope", async () => {
  state.card = {
    concept: "模型正文概念说明",
    source_mode: "materials",
    source_available: true,
    config: {
      topic: "旧卡片的主题",
      source_mode: "materials",
      knowledge_base_id: "old-kb",
      file_ids: ["selected-1", "selected-2"],
    },
  };
  view({ weaknessId: "", explanationId: "explanation", version: 2 });
  const rendered = await screen.findByTestId("practice-config");
  const config = JSON.parse(rendered.textContent ?? "{}");
  expect(config.topic).toBe("旧卡片的主题");
  expect(config.knowledge_base_id).toBe("old-kb");
  expect(config.file_ids).toEqual(["selected-1", "selected-2"]);
  expect(config.learning_target).toEqual({
    kind: "explanation",
    id: "explanation",
    card_version: 2,
  });
});
it("blocks a stale weakness without silently changing the requested version", async () => {
  state.weakness = { title: "事务", version: 3, decision: "confirmed", source_available: true };
  view({ weaknessId: "weakness", explanationId: "", version: 2 });
  expect(await screen.findByRole("alert")).toHaveTextContent("目标版本已变化");
  expect(screen.queryByTestId("practice-config")).not.toBeInTheDocument();
});
it("blocks conflicting parameters before querying a target", async () => {
  view({ weaknessId: "weakness", explanationId: "explanation", version: 1 });
  expect(await screen.findByRole("alert")).toHaveTextContent("目标参数不完整");
});
