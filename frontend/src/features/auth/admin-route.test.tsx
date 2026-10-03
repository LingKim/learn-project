import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AdminRoute } from "./auth-route";

const state = vi.hoisted(() => ({
  status: "authenticated",
  role: "user",
  replace: vi.fn(),
  mounted: vi.fn(),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: state.replace }) }));
vi.mock("./auth-provider", () => ({
  useAuth: () => ({ status: state.status, user: { role: state.role } }),
}));

function SensitiveChild() {
  state.mounted();
  return <div>管理员敏感查询组件</div>;
}

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  state.status = "authenticated";
  state.role = "user";
});

describe("管理路由边界", () => {
  it("普通用户不会挂载敏感查询组件", () => {
    render(
      <AdminRoute>
        <SensitiveChild />
      </AdminRoute>,
    );
    expect(screen.getByRole("heading", { name: "无权访问管理功能" })).toBeInTheDocument();
    expect(state.mounted).not.toHaveBeenCalled();
  });
  it("恢复认证期间不挂载管理内容", () => {
    state.status = "loading";
    state.role = "admin";
    render(
      <AdminRoute>
        <SensitiveChild />
      </AdminRoute>,
    );
    expect(screen.getByText("正在恢复登录状态…")).toBeInTheDocument();
    expect(state.mounted).not.toHaveBeenCalled();
    expect(state.replace).not.toHaveBeenCalled();
  });
  it("真实管理员身份恢复后才挂载内容", () => {
    state.role = "admin";
    render(
      <AdminRoute>
        <SensitiveChild />
      </AdminRoute>,
    );
    expect(screen.getByText("管理员敏感查询组件")).toBeInTheDocument();
    expect(state.mounted).toHaveBeenCalled();
  });
});
