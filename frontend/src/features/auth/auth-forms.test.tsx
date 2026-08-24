import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ForcedPasswordChangeForm, LoginForm, RegisterForm, isPasswordValid } from "./auth-forms";

afterEach(cleanup);

describe("认证表单", () => {
  it("登录只使用用户名且不提供找回密码", () => {
    render(<LoginForm />);
    expect(screen.getByLabelText("用户名")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "记住账号" })).toBeInTheDocument();
    expect(screen.queryByText("忘记密码")).not.toBeInTheDocument();
    expect(screen.queryByText(/手机号|邮箱/)).not.toBeInTheDocument();
  });

  it("登录提交空表单时展示字段错误", () => {
    render(<LoginForm />);
    fireEvent.click(screen.getByRole("button", { name: "登录" }));
    expect(screen.getByText("请输入用户名")).toBeInTheDocument();
    expect(screen.getByText("请输入密码")).toBeInTheDocument();
  });

  it("注册校验密码规则与确认密码", () => {
    render(<RegisterForm />);
    fireEvent.change(screen.getByLabelText("昵称"), { target: { value: "小李" } });
    fireEvent.change(screen.getByLabelText("用户名"), { target: { value: "lili" } });
    fireEvent.change(screen.getByLabelText("设置密码"), { target: { value: "12345678" } });
    fireEvent.change(screen.getByLabelText("确认密码"), { target: { value: "12345679" } });
    fireEvent.click(screen.getByRole("button", { name: "创建账号" }));
    expect(screen.getByText(/密码至少 8 位/)).toBeInTheDocument();
    expect(screen.getByText("两次输入的密码不一致")).toBeInTheDocument();
  });

  it("强制改密没有跳过入口", () => {
    render(<ForcedPasswordChangeForm />);
    expect(screen.getByLabelText("当前临时密码")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "修改密码并继续" })).toBeInTheDocument();
    expect(screen.queryByText("跳过")).not.toBeInTheDocument();
  });

  it("密码至少包含两类字符", () => {
    expect(isPasswordValid("12345678")).toBe(false);
    expect(isPasswordValid("learn2026")).toBe(true);
  });
});
