import { MutationObserver, QueryClient } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";
import { deleteWeakness, patchWeakness } from "./api";
import { deleteWeaknessOptions, learningAssetKeys, patchWeaknessOptions } from "./queries";
import { ApiError } from "@/lib/api/errors";
vi.mock("./api", () => ({ deleteWeakness: vi.fn(), patchWeakness: vi.fn() }));
it("软删除清理对应卡片和原文缓存，保留其他资产", async () => {
  vi.mocked(deleteWeakness).mockResolvedValue({ data: undefined, message: "已删除" });
  const client = new QueryClient();
  client.setQueryData(learningAssetKeys.weakness("one"), { explanation_id: "exp-one" });
  client.setQueryData(learningAssetKeys.card("exp-one", 1), { concept: "删除资产卡片" });
  client.setQueryData(learningAssetKeys.source("exp-one", 1, "source"), {
    evidence: "删除资产原文",
  });
  client.setQueryData(learningAssetKeys.card("exp-other", 1), { concept: "其他资产卡片" });
  const observer = new MutationObserver(client, deleteWeaknessOptions(client));
  await observer.mutate({ id: "one", version: 2 });
  expect(deleteWeakness).toHaveBeenCalledWith("one", 2);
  expect(client.getQueryData(learningAssetKeys.weakness("one"))).toBeUndefined();
  expect(client.getQueryData(learningAssetKeys.card("exp-one", 1))).toBeUndefined();
  expect(client.getQueryData(learningAssetKeys.source("exp-one", 1, "source"))).toBeUndefined();
  expect(client.getQueryData(learningAssetKeys.card("exp-other", 1))).toEqual({
    concept: "其他资产卡片",
  });
});
it("并发写失败不自动重放，错误由组件保留当前输入后展示", async () => {
  vi.mocked(patchWeakness).mockRejectedValue(new ApiError("版本冲突", { status: 409 }));
  const observer = new MutationObserver(new QueryClient(), patchWeaknessOptions());
  await expect(
    observer.mutate({ id: "one", body: { expected_version: 1, title: "合成修改" } }),
  ).rejects.toMatchObject({ status: 409 });
  expect(patchWeakness).toHaveBeenCalledTimes(1);
});
