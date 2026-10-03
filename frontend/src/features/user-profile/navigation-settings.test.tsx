import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";
import * as api from "./api";
import { NavigationSettings } from "./navigation-settings";
import { userProfileKeys } from "./queries";

vi.mock("./api", async (importOriginal) => {
  const original = await importOriginal<typeof import("./api")>();
  return { ...original, getUserProfile: vi.fn(), updateUserProfile: vi.fn() };
});

const profile: api.UserProfileView = {
  username: "test-user",
  nickname: "测试用户",
  target_job: null,
  experience_months: null,
  experience_display: null,
  target_level: null,
  target_skills: null,
  focus_topics: null,
  learning_goal: null,
  preferred_language: null,
  navigation_position: "left",
  avatar_set: false,
  avatar_url: null,
  version: 3,
  active_weaknesses: [],
};

function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const onOpenChange = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <NavigationSettings open onOpenChange={onOpenChange} />
    </QueryClientProvider>,
  );
  return { client, onOpenChange };
}

async function selectTop() {
  fireEvent.click(await screen.findByRole("radio", { name: /顶部导航/ }));
  fireEvent.click(screen.getByRole("button", { name: "保存设置" }));
}

afterEach(cleanup);
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getUserProfile).mockResolvedValue(profile);
});

describe("账号导航设置", () => {
  it("默认选中左侧导航且不会自动保存", async () => {
    const { client } = mount();

    expect(await screen.findByRole("radio", { name: /左侧导航/ })).toBeChecked();
    expect(screen.getByRole("radio", { name: /顶部导航/ })).not.toBeChecked();
    expect(client.getQueryData(userProfileKeys.detail())).toEqual(profile);
    expect(api.updateUserProfile).not.toHaveBeenCalled();
  });

  it("保存顶部导航携带当前版本并使用服务端响应更新共享缓存", async () => {
    const updated = { ...profile, navigation_position: "top" as const, version: 4 };
    vi.mocked(api.updateUserProfile).mockResolvedValue({ data: updated, message: "已保存" });
    const { client, onOpenChange } = mount();

    await selectTop();

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(api.updateUserProfile).toHaveBeenCalledExactlyOnceWith({
      version: 3,
      navigation_position: "top",
    });
    expect(client.getQueryData(userProfileKeys.detail())).toEqual(updated);
  });

  it("保存失败时保留原缓存并显示错误，设置保持打开", async () => {
    vi.mocked(api.updateUserProfile).mockRejectedValue(
      new ApiError("保存暂时失败", { status: 503 }),
    );
    const { client, onOpenChange } = mount();

    await selectTop();

    expect(await screen.findByRole("alert")).toHaveTextContent("保存暂时失败");
    expect(client.getQueryData(userProfileKeys.detail())).toEqual(profile);
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "保存设置" })).toBeEnabled();
  });

  it("409 冲突后重新读取账号资料，重试使用新版本", async () => {
    const refreshed = { ...profile, version: 5, nickname: "其他设备的新昵称" };
    const updated = { ...refreshed, navigation_position: "top" as const, version: 6 };
    vi.mocked(api.getUserProfile).mockResolvedValueOnce(profile).mockResolvedValue(refreshed);
    vi.mocked(api.updateUserProfile)
      .mockRejectedValueOnce(new ApiError("资料已更新，请重试", { status: 409 }))
      .mockResolvedValueOnce({ data: updated, message: "已保存" });
    const { client, onOpenChange } = mount();

    await selectTop();

    expect(await screen.findByRole("alert")).toHaveTextContent("资料已更新，请重试");
    expect(api.getUserProfile).toHaveBeenCalledTimes(2);
    expect(client.getQueryData(userProfileKeys.detail())).toEqual(refreshed);
    expect(onOpenChange).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "保存设置" }));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(api.updateUserProfile).toHaveBeenNthCalledWith(2, {
      version: 5,
      navigation_position: "top",
    });
    expect(client.getQueryData(userProfileKeys.detail())).toEqual(updated);
  });

  it("修改选项后取消不会保存或修改缓存", async () => {
    const { client, onOpenChange } = mount();
    fireEvent.click(await screen.findByRole("radio", { name: /顶部导航/ }));

    fireEvent.click(screen.getByRole("button", { name: "取消" }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(api.updateUserProfile).not.toHaveBeenCalled();
    expect(client.getQueryData(userProfileKeys.detail())).toEqual(profile);
  });
});
