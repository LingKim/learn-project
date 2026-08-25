"use client";

import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import { type FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { CheckboxField } from "@/components/ui/checkbox-field";
import { InputField } from "@/components/ui/input-field";
import { PasswordField } from "@/components/ui/password-field";
import { toApiError, toFieldErrors } from "@/lib/api/errors";

import { loadRememberedUsername, useAuth } from "./auth-provider";
import { loginMutationOptions, registerMutationOptions } from "./mutations";

type Errors = Record<string, string>;

const USERNAME_PATTERN = /^[a-z0-9_]{3,32}$/;

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

function normalizedUsername(value: string) {
  return value.trim().toLowerCase();
}

function usernameError(value: string) {
  if (!value) return "请输入用户名";
  if (!USERNAME_PATTERN.test(value)) return "用户名为 3 至 32 位小写字母、数字或下划线";
  return undefined;
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
      className="rounded-md border border-danger/30 bg-danger/5 px-3 py-2.5 text-sm leading-5 text-danger"
      role="alert"
    >
      {message}
    </p>
  );
}

function authenticationMessage(error: unknown) {
  const apiError = toApiError(error);
  if (apiError.errorKey === "AUTH_INVALID_CREDENTIALS") return "用户名或密码错误";
  if (apiError.errorKey === "AUTH_RATE_LIMITED") return "尝试次数过多，请稍后再试";
  if (apiError.errorKey === "AUTH_USERNAME_TAKEN") return "该用户名已被使用";
  return apiError.message;
}

export function LoginForm() {
  const { completeAuthentication } = useAuth();
  const mutation = useMutation(loginMutationOptions());
  const [errors, setErrors] = useState<Errors>({});
  const [notice, setNotice] = useState("");
  const [username, setUsername] = useState("");
  const [rememberUsername, setRememberUsername] = useState(false);

  useEffect(() => {
    const remembered = loadRememberedUsername();
    if (remembered) {
      setUsername(remembered);
      setRememberUsername(true);
    }
  }, []);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const normalized = normalizedUsername(username);
    const password = formValue(form, "password");
    const nextErrors: Errors = {};
    const invalidUsername = usernameError(normalized);
    if (invalidUsername) nextErrors.username = invalidUsername;
    if (!password) nextErrors.password = "请输入密码";
    setErrors(nextErrors);
    setNotice("");
    if (Object.keys(nextErrors).length) return;

    mutation.mutate(
      { username: normalized, password },
      {
        onSuccess: (result) =>
          completeAuthentication(result.data, rememberUsername ? normalized : undefined),
        onError: (error) => {
          setErrors(toFieldErrors(error));
          setNotice(authenticationMessage(error));
        },
      },
    );
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
          value={username}
          onChange={(event) => setUsername(event.target.value)}
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
        <CheckboxField
          name="rememberUsername"
          label="记住账号"
          checked={rememberUsername}
          onCheckedChange={(checked) => setRememberUsername(checked === true)}
        />
        {notice ? <StatusNotice message={notice} /> : null}
        <Button type="submit" variant="brand" className="w-full" disabled={mutation.isPending}>
          {mutation.isPending ? "正在登录…" : "登录"}
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
  const { completeAuthentication } = useAuth();
  const mutation = useMutation(registerMutationOptions());
  const [errors, setErrors] = useState<Errors>({});
  const [notice, setNotice] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const nickname = formValue(form, "nickname").trim();
    const username = normalizedUsername(formValue(form, "username"));
    const password = formValue(form, "password");
    const confirmPassword = formValue(form, "confirmPassword");
    const nextErrors: Errors = {};
    if (!nickname) nextErrors.nickname = "请输入昵称";
    else if (nickname.length > 40) nextErrors.nickname = "昵称不能超过 40 位";
    const invalidUsername = usernameError(username);
    if (invalidUsername) nextErrors.username = invalidUsername;
    if (!isPasswordValid(password))
      nextErrors.password = "密码至少 8 位，并包含字母、数字、符号中的至少两类";
    if (!confirmPassword) nextErrors.confirmPassword = "请再次输入密码";
    else if (confirmPassword !== password) nextErrors.confirmPassword = "两次输入的密码不一致";
    setErrors(nextErrors);
    setNotice("");
    if (Object.keys(nextErrors).length) return;

    mutation.mutate(
      { nickname, username, password },
      {
        onSuccess: (result) => completeAuthentication(result.data),
        onError: (error) => {
          setErrors(toFieldErrors(error));
          setNotice(authenticationMessage(error));
        },
      },
    );
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
          placeholder="3 至 32 位小写字母、数字或下划线"
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
        <Button type="submit" variant="brand" className="w-full" disabled={mutation.isPending}>
          {mutation.isPending ? "正在创建…" : "创建账号"}
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
