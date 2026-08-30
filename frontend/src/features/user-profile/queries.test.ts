import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import * as api from "./api";
import {
  updateUserProfileMutationOptions,
  userAvatarQueryOptions,
  userProfileKeys,
  userProfileQueryOptions,
} from "./queries";

vi.mock("./api", async (importOriginal) => {
  const original = await importOriginal<typeof import("./api")>();
  return { ...original, getUserProfile: vi.fn(), updateUserProfile: vi.fn() };
});

describe("个人资料 Query 配置", () => {
  it("使用稳定且彼此隔离的详情与头像 key", () => {
    expect(userProfileQueryOptions().queryKey).toEqual(["user-profile", "detail"]);
    expect(userAvatarQueryOptions(3, true).queryKey).toEqual(["user-profile", "avatar", 3]);
  });

  it("保存成功后用响应版本更新详情缓存", async () => {
    const queryClient = new QueryClient();
    const updated = { username: "user", nickname: "新昵称", version: 2 };
    vi.mocked(api.updateUserProfile).mockResolvedValue({
      data: updated as never,
      message: "已保存",
    });
    const options = updateUserProfileMutationOptions(queryClient);
    await options.mutationFn!({ version: 1, nickname: "新昵称" }, {} as never);
    await options.onSuccess?.(
      { data: updated as never, message: "已保存" },
      { version: 1, nickname: "新昵称" },
      undefined,
      {} as never,
    );
    expect(queryClient.getQueryData(userProfileKeys.detail())).toEqual(updated);
  });
});
