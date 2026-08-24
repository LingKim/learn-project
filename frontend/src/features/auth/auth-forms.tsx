"use client";

import { Check, CircleAlert, LockKeyhole, LogOut } from "lucide-react";
import Link from "next/link";
import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { CheckboxField } from "@/components/ui/checkbox-field";
import { InputField } from "@/components/ui/input-field";
import { PasswordField } from "@/components/ui/password-field";
import { cn } from "@/lib/utils";

const integrationNotice = "前端校验已通过，认证接口尚未接入。";

type Errors = Record<string, string>;

function formValue(form: FormData, name: string) {
  const value = form.get(name);
  return typeof value === "string" ? value : "";
}

function passwordCategories(value: string) {
  return [/[A-Za-z]/.test(value), /\d/.test(value), /[^A-Za-z\d]/.test(value)].filter(Boolean)
    .length;
}

export function isPasswordValid(value: string) {
  return value.length >= 8 && passwordCategories(value) >= 2;
}

function FormHeader({ title, description }: { title: string; description: string }) {
  return (
    <div className="mb-9">
      <h2 className="text-3xl font-semibold tracking-[-0.045em] text-foreground sm:text-4xl">
        {title}
      </h2>
      <p className="mt-3 text-sm leading-6 text-muted-foreground">{description}</p>
    </div>
  );
}

function StatusNotice({ message }: { message: string }) {
  return (
    <p
      className="flex items-start gap-2 rounded-md border border-border bg-sidebar px-3 py-2.5 text-sm leading-5 text-foreground"
      role="status"
    >
      <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-accent-foreground" />
      {message}
    </p>
  );
}

export function LoginForm() {
  const [errors, setErrors] = useState<Errors>({});
  const [notice, setNotice] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const nextErrors: Errors = {};
    if (!formValue(form, "username").trim()) nextErrors.username = "请输入用户名";
    if (!formValue(form, "password")) nextErrors.password = "请输入密码";
    setErrors(nextErrors);
    setNotice(Object.keys(nextErrors).length ? "" : integrationNotice);
  }

  return (
    <>
      <FormHeader title="欢迎回来" description="登录后继续你的学习与面试准备。" />
      <form className="space-y-5" noValidate onSubmit={handleSubmit}>
        <InputField
          id="login-username"
          name="username"
          label="用户名"
          autoComplete="username"
          placeholder="请输入用户名"
          error={errors.username}
        />
        <PasswordField
          id="login-password"
          name="password"
          label="密码"
          autoComplete="current-password"
          placeholder="请输入密码"
          error={errors.password}
        />
        <CheckboxField name="rememberUsername" label="记住账号" />
        {notice ? <StatusNotice message={notice} /> : null}
        <Button variant="brand" className="w-full">
          登录
        </Button>
      </form>
      <div className="mt-7 flex items-center gap-4 text-xs text-muted-foreground before:h-px before:flex-1 before:bg-border after:h-px after:flex-1 after:bg-border">
        还没有账号
      </div>
      <Button asChild variant="outline" className="mt-5 w-full">
        <Link href="/register">创建账号</Link>
      </Button>
    </>
  );
}

export function RegisterForm() {
  const [errors, setErrors] = useState<Errors>({});
  const [notice, setNotice] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const nickname = formValue(form, "nickname").trim();
    const username = formValue(form, "username").trim();
    const password = formValue(form, "password");
    const confirmPassword = formValue(form, "confirmPassword");
    const nextErrors: Errors = {};
    if (!nickname) nextErrors.nickname = "请输入昵称";
    if (!username) nextErrors.username = "请输入用户名";
    if (!isPasswordValid(password))
      nextErrors.password = "密码至少 8 位，并包含字母、数字、符号中的至少两类";
    if (!confirmPassword) nextErrors.confirmPassword = "请再次输入密码";
    else if (confirmPassword !== password) nextErrors.confirmPassword = "两次输入的密码不一致";
    setErrors(nextErrors);
    setNotice(Object.keys(nextErrors).length ? "" : integrationNotice);
  }

  return (
    <>
      <FormHeader title="创建账号" description="填写基本信息，开启你的学习空间。" />
      <form className="space-y-4" noValidate onSubmit={handleSubmit}>
        <InputField
          id="register-nickname"
          name="nickname"
          label="昵称"
          autoComplete="nickname"
          placeholder="请输入你的称呼"
          error={errors.nickname}
        />
        <InputField
          id="register-username"
          name="username"
          label="用户名"
          autoComplete="username"
          placeholder="设置唯一用户名"
          error={errors.username}
        />
        <PasswordField
          id="register-password"
          name="password"
          label="设置密码"
          autoComplete="new-password"
          placeholder="至少 8 位，包含两类字符"
          error={errors.password}
        />
        <PasswordField
          id="register-confirm-password"
          name="confirmPassword"
          label="确认密码"
          autoComplete="new-password"
          placeholder="再次输入密码"
          error={errors.confirmPassword}
        />
        {notice ? <StatusNotice message={notice} /> : null}
        <Button variant="brand" className="w-full">
          创建账号
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted-foreground">
        已有账号？{" "}
        <Link
          className="font-medium text-foreground underline decoration-border underline-offset-4 hover:text-accent-foreground"
          href="/login"
        >
          直接登录
        </Link>
      </p>
    </>
  );
}

export function ForcedPasswordChangeForm() {
  const [errors, setErrors] = useState<Errors>({});
  const [notice, setNotice] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const rules = [
    { label: "不少于 8 位", met: newPassword.length >= 8 },
    { label: "包含至少两类字符", met: passwordCategories(newPassword) >= 2 },
  ];

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const currentPassword = formValue(form, "currentPassword");
    const confirmPassword = formValue(form, "confirmPassword");
    const nextErrors: Errors = {};
    if (!currentPassword) nextErrors.currentPassword = "请输入当前临时密码";
    if (!isPasswordValid(newPassword))
      nextErrors.newPassword = "新密码至少 8 位，并包含字母、数字、符号中的至少两类";
    if (!confirmPassword) nextErrors.confirmPassword = "请再次输入新密码";
    else if (confirmPassword !== newPassword) nextErrors.confirmPassword = "两次输入的新密码不一致";
    setErrors(nextErrors);
    setNotice(Object.keys(nextErrors).length ? "" : integrationNotice);
  }

  return (
    <>
      <div className="mb-8 inline-flex size-11 items-center justify-center rounded-md bg-sidebar text-accent-foreground">
        <LockKeyhole aria-hidden="true" className="size-5" />
      </div>
      <FormHeader
        title="请先修改临时密码"
        description="为了保护账号安全，首次使用临时密码登录后，必须先设置新密码。"
      />
      <div className="mb-6 rounded-md border border-border bg-sidebar px-4 py-3 text-sm leading-6 text-foreground">
        当前为临时密码，仅可使用一次。
      </div>
      <form className="space-y-4" noValidate onSubmit={handleSubmit}>
        <PasswordField
          id="current-password"
          name="currentPassword"
          label="当前临时密码"
          autoComplete="current-password"
          placeholder="请输入管理员提供的临时密码"
          error={errors.currentPassword}
        />
        <PasswordField
          id="new-password"
          name="newPassword"
          label="新密码"
          autoComplete="new-password"
          placeholder="至少 8 位，包含两类字符"
          value={newPassword}
          onChange={(event) => setNewPassword(event.target.value)}
          error={errors.newPassword}
        />
        <PasswordField
          id="confirm-new-password"
          name="confirmPassword"
          label="确认新密码"
          autoComplete="new-password"
          placeholder="再次输入新密码"
          error={errors.confirmPassword}
        />
        <ul
          className="flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground"
          aria-label="密码要求"
        >
          {rules.map((rule) => (
            <li
              key={rule.label}
              className={cn("inline-flex items-center gap-1.5", rule.met && "text-foreground")}
            >
              <span
                className={cn(
                  "grid size-4 place-items-center rounded-full border border-border",
                  rule.met && "border-success bg-success text-background",
                )}
              >
                {rule.met ? <Check aria-hidden="true" className="size-3" /> : null}
              </span>
              {rule.label}
            </li>
          ))}
        </ul>
        {notice ? <StatusNotice message={notice} /> : null}
        <Button variant="brand" className="w-full">
          修改密码并继续
        </Button>
      </form>
      <Link
        className="mx-auto mt-5 flex min-h-11 w-fit items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
        href="/login"
      >
        <LogOut aria-hidden="true" className="size-4" />
        退出当前账号
      </Link>
    </>
  );
}
