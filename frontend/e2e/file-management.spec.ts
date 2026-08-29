import { expect, test } from "@playwright/test";

const password = "E2e-password-42";
const runId = `${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
const username = `file_e2e_${runId}`;
const knowledgeBaseName = `E2E 资料库 ${runId}`;
const renamedKnowledgeBaseName = `${knowledgeBaseName} 已改`;
const originalFileName = `e2e-notes-${runId}.txt`;
const renamedFileName = `e2e-notes-${runId}-renamed.txt`;

test("知识库与文件增删改查闭环", async ({ page }) => {
  await page.goto("/register");
  await page.getByLabel("昵称").fill("文件 E2E 用户");
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("设置密码", { exact: true }).fill(password);
  await page.getByLabel("确认密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "创建账号" }).click();

  await expect(page).toHaveURL(/\/$/);
  await page.getByRole("link", { name: "进入内容库" }).click();
  await expect(page).toHaveURL(/\/content$/);
  await expect(page.getByRole("heading", { name: "内容库 / 知识库" })).toBeVisible();
  await expect(page.getByText("默认知识库", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "创建知识库" }).click();
  await page.getByLabel("知识库名称").fill(knowledgeBaseName);
  await page.getByRole("button", { name: "保存" }).click();
  await expect(page.getByText(knowledgeBaseName, { exact: true })).toBeVisible();

  await page.getByRole("button", { name: `重命名 ${knowledgeBaseName}` }).click();
  await page.getByLabel("知识库名称").fill(renamedKnowledgeBaseName);
  await page.getByRole("button", { name: "保存" }).click();
  await expect(page.getByText(renamedKnowledgeBaseName, { exact: true })).toBeVisible();
  await page.screenshot({
    path: "../output/playwright/file-management-overview.png",
    fullPage: true,
  });

  await page
    .getByRole("link", { name: /默认知识库/ })
    .first()
    .click();
  await expect(page).toHaveURL(/\/content\/[0-9a-f-]+$/);
  await page.locator("#knowledge-file-upload").setInputFiles({
    name: originalFileName,
    mimeType: "text/plain",
    buffer: Buffer.from("Spring transaction E2E notes\n"),
  });
  await expect(page.getByText(originalFileName, { exact: true })).toBeVisible({ timeout: 70_000 });
  await expect(page.getByText("已上传·待解析", { exact: true })).toBeVisible();
  await page.screenshot({
    path: "../output/playwright/file-management-detail.png",
    fullPage: true,
  });

  await page.getByRole("button", { name: `重命名 ${originalFileName}` }).click();
  await page.getByLabel("文件名").fill(renamedFileName);
  await page.getByRole("button", { name: "确认" }).click();
  await expect(page.getByText(renamedFileName, { exact: true })).toBeVisible();

  const downloadResponse = page.waitForResponse(
    (response) => response.url().includes("/download-url") && response.request().method() === "GET",
  );
  await page.getByRole("button", { name: `下载 ${renamedFileName}` }).click();
  expect((await downloadResponse).status()).toBe(200);

  await page.getByRole("button", { name: `移动 ${renamedFileName}` }).click();
  await page.getByLabel("目标知识库").click();
  await page.getByRole("option", { name: renamedKnowledgeBaseName }).click();
  await page.getByRole("button", { name: "确认" }).click();
  await expect(page.getByText(renamedFileName, { exact: true })).toHaveCount(0);

  await page.getByRole("link", { name: "返回知识库" }).click();
  await page
    .getByRole("link", { name: new RegExp(renamedKnowledgeBaseName) })
    .first()
    .click();
  await expect(page.getByText(renamedFileName, { exact: true })).toBeVisible();

  await page.getByRole("button", { name: `删除 ${renamedFileName}` }).click();
  await expect(page.getByRole("heading", { name: `确认删除“${renamedFileName}”` })).toBeVisible();
  await page.getByRole("button", { name: "删除来源", exact: true }).click();
  await expect(page.getByText(renamedFileName, { exact: true })).toHaveCount(0);

  await page.getByRole("link", { name: "返回知识库" }).click();
  await page.getByRole("button", { name: `删除 ${renamedKnowledgeBaseName}` }).click();
  await expect(
    page.getByRole("heading", { name: `确认删除“${renamedKnowledgeBaseName}”` }),
  ).toBeVisible();
  await page.getByRole("button", { name: "删除来源", exact: true }).click();
  await expect(page.getByText(renamedKnowledgeBaseName, { exact: true })).toHaveCount(0);
});
