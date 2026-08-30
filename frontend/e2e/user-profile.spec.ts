import { expect, test } from "@playwright/test";

const password = "E2e-password-42";
const runId = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
const username = `profile_${runId}`;

// 32×32 静态 PNG；真实上传到隔离 RustFS，并由后端 worker 转换为 WebP。
const avatarPng = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAAO0lEQVR4nO3RQREAMAjEwKMKq7SiUFIJ4cMvK+CYCdXvZtNZXY8HBvwBMhEyETIRMhEyETIRMhEyUcgHSloCIO5PzrYAAAAASUVORK5CYII=",
  "base64",
);

test("个人资料保存、刷新恢复与头像上传删除闭环", async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto("/register");
  await page.getByLabel("昵称").fill("资料 E2E 用户");
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("设置密码", { exact: true }).fill(password);
  await page.getByLabel("确认密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(page).toHaveURL(/\/$/);

  await page.goto("/profile");
  await expect(page.getByRole("heading", { name: "个人资料" })).toBeVisible();
  await expect(page.getByText("还没有可用的薄弱点证据")).toBeVisible();
  await expect(page.getByLabel("用户名")).toHaveValue(username);

  await page.getByLabel("昵称").fill("资料闭环用户");
  await page.getByLabel("目标岗位").fill("Java 后端工程师");
  await page.getByLabel("工作经验年数").fill("3");
  await page.getByLabel("工作经验月数").fill("2");
  await page.getByLabel("岗位等级").click();
  await page.getByRole("option", { name: "高级" }).click();
  await page.getByLabel("目标技能").fill("Spring Boot");
  await page.getByRole("button", { name: "添加" }).first().click();
  await page.getByLabel("重点关注知识点").fill("JVM 调优");
  await page.getByRole("button", { name: "添加" }).last().click();
  await page.getByLabel("学习目标").fill("三个月内完成高级 Java 工程师面试准备");
  await page.getByRole("button", { name: "保存资料" }).click();
  await expect(page.getByText("个人资料已更新", { exact: true })).toBeVisible();
  await expect(page.getByText("资料版本 1", { exact: true })).toBeVisible();

  await page.reload();
  await expect(page.getByLabel("昵称")).toHaveValue("资料闭环用户");
  await expect(page.getByLabel("目标岗位")).toHaveValue("Java 后端工程师");
  await expect(page.getByLabel("工作经验年数")).toHaveValue("3");
  await expect(page.getByLabel("工作经验月数")).toHaveValue("2");
  await expect(page.getByText("Spring Boot", { exact: true })).toBeVisible();
  await expect(page.getByText("JVM 调优", { exact: true })).toBeVisible();

  await page.getByLabel("选择头像图片").setInputFiles({
    name: "avatar.png",
    mimeType: "image/png",
    buffer: avatarPng,
  });
  await expect(page.getByText("头像已更新", { exact: true })).toBeVisible({ timeout: 70_000 });
  await expect(page.getByAltText("当前头像")).toBeVisible();
  await expect(page.getByText("资料版本 2", { exact: true })).toBeVisible();

  await page.screenshot({ path: "../output/playwright/user-profile.png", fullPage: true });

  await page.getByRole("button", { name: "删除头像" }).click();
  await expect(page.getByText("头像已删除", { exact: true })).toBeVisible();
  await expect(page.getByAltText("当前头像")).toHaveCount(0);
  await expect(page.getByText("资料版本 3", { exact: true })).toBeVisible();
});
