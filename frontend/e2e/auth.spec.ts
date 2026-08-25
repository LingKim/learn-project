import { expect, request, test } from "@playwright/test";

const password = "E2e-password-42";
const runId = `${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
const username = `e2e_${runId}`;
const nickname = "端到端测试用户";

test.describe("认证闭环", () => {
  test("未登录访问受保护首页会跳转登录", async ({ page }) => {
    await page.goto("/");

    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole("heading", { name: "欢迎回来" })).toBeVisible();
  });

  test("注册、刷新恢复、退出、重登与 Refresh 重放撤销", async ({ page, context }) => {
    await page.goto("/register");
    await page.getByLabel("昵称").fill(nickname);
    await page.getByLabel("用户名").fill(username);
    await page.getByLabel("设置密码", { exact: true }).fill(password);
    await page.getByLabel("确认密码", { exact: true }).fill(password);
    await page.getByRole("button", { name: "创建账号" }).click();

    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByText(nickname)).toBeVisible();

    await page.reload();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByText(nickname)).toBeVisible();

    await page.getByRole("button", { name: "退出登录" }).click();
    await expect(page).toHaveURL(/\/login$/);

    await page.getByLabel("用户名").fill(username);
    await page.getByLabel("密码", { exact: true }).fill("wrong-password-42");
    await page.getByRole("button", { name: "登录", exact: true }).click();
    await expect(page.getByText("用户名或密码错误", { exact: true })).toBeVisible();

    await page.getByLabel("密码", { exact: true }).fill(password);
    await page.getByRole("button", { name: "登录", exact: true }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByText(nickname)).toBeVisible();

    const oldRefresh = (await context.cookies()).find(
      (cookie) => cookie.name === "xuemian_refresh_token",
    );
    expect(oldRefresh).toBeTruthy();

    await page.reload();
    await expect(page.getByText(nickname)).toBeVisible();

    const replayClient = await request.newContext({
      baseURL: "http://127.0.0.1:3100",
      extraHTTPHeaders: {
        Cookie: `${oldRefresh!.name}=${oldRefresh!.value}`,
        Origin: "http://127.0.0.1:3100",
      },
    });
    try {
      const replay = await replayClient.post("/api/backend/api/v1/auth/refresh");
      expect(replay.status()).toBe(401);
      expect(await replay.json()).toMatchObject({
        error_key: "AUTH_REFRESH_TOKEN_INVALID",
      });
    } finally {
      await replayClient.dispose();
    }

    await page.reload();
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole("heading", { name: "欢迎回来" })).toBeVisible();
  });

  test("连续错误密码触发账号限流提示", async ({ page }) => {
    const limitedUsername = `rate_${runId}`;
    await page.goto("/login");
    await page.getByLabel("用户名").fill(limitedUsername);
    await page.getByLabel("密码", { exact: true }).fill("wrong-password-42");

    for (let attempt = 1; attempt <= 4; attempt += 1) {
      const responsePromise = page.waitForResponse(
        (response) =>
          response.url().endsWith("/api/v1/auth/login") && response.request().method() === "POST",
      );
      await page.getByRole("button", { name: "登录", exact: true }).click();
      expect((await responsePromise).status()).toBe(401);
      await expect(page.getByText("用户名或密码错误", { exact: true })).toBeVisible();
    }
    const responsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/v1/auth/login") && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "登录", exact: true }).click();
    expect((await responsePromise).status()).toBe(429);
    await expect(page.getByText("尝试次数过多，请稍后再试", { exact: true })).toBeVisible();
  });

  test("已取消的首次改密路由不再提供功能页", async ({ page }) => {
    const response = await page.goto("/first-login/change-password");

    expect(response?.status()).toBe(404);
    await expect(page.getByText("首次登录，请先修改密码")).toHaveCount(0);
  });
});
