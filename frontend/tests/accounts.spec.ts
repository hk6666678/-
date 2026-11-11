import { test, expect } from "@playwright/test";
test("personal account lifecycle through the browser", async ({
  page,
  browser,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "登录工作平台" }),
  ).toBeVisible();
  await page.screenshot({ path: "test-results/login.png", fullPage: true });
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page
    .getByLabel("密码", { exact: true })
    .fill("Synthetic-password-123!");
  await page.getByRole("button", { name: "登录平台" }).click();
  await page.getByRole("button", { name: "个人账号管理" }).click();
  await page.getByLabel("新账号用户名").fill("synthetic-member");
  await page.getByLabel("初始密码").fill("Synthetic-member-password!");
  await page
    .getByRole("group", { name: "账号角色" })
    .getByLabel("学院数据管理员")
    .check();
  await page.getByRole("button", { name: "创建账号" }).click();
  const row = page
    .getByRole("row")
    .filter({ has: page.getByText("synthetic-member", { exact: true }) });
  await expect(row).toBeVisible();
  await expect(row.getByLabel("synthetic-member 学院数据管理员")).toBeChecked();
  await page.screenshot({ path: "test-results/accounts.png", fullPage: true });
  const memberContext = await browser.newContext();
  const member = await memberContext.newPage();
  await member.goto("http://127.0.0.1:8011/");
  await member.getByLabel("用户名", { exact: true }).fill("synthetic-member");
  await member
    .getByLabel("密码", { exact: true })
    .fill("Synthetic-member-password!");
  await member.getByRole("button", { name: "登录平台" }).click();
  await expect(
    member.getByText("业务数据权限请在授权验证页面查看"),
  ).toBeVisible();
  await expect(
    member.getByRole("button", { name: "个人账号管理" }),
  ).toHaveCount(0);
  await row.getByRole("button", { name: "停用" }).click();
  await expect(row.getByText("已停用", { exact: true })).toBeVisible();
  await member.reload();
  await expect(
    member.getByRole("heading", { name: "登录工作平台" }),
  ).toBeVisible();
  await memberContext.close();
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(
    page.getByRole("heading", { name: "登录工作平台" }),
  ).toBeVisible();
});
