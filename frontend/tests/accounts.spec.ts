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
  await page.getByLabel("账号权限").selectOption("ordinary");
  await expect(page.getByLabel("所属学院", { exact: true })).toHaveAttribute("list", "tongji-colleges");
  await expect(page.locator('#tongji-colleges option[value="计算机科学与技术学院（软件学院）"]')).toHaveCount(1);
  await page.getByLabel("所属学院", { exact: true }).fill("合成试用学院");
  await page.getByRole("button", { name: "创建账号" }).click();
  const row = page
    .getByRole("row")
    .filter({ has: page.getByText("synthetic-member", { exact: true }) });
  await expect(row).toBeVisible();
  await expect(row.getByText("普通", { exact: true })).toBeVisible();
  await expect(row.getByText("合成试用学院", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 1000 });
  await page.screenshot({ path: "test-results/accounts.png" });
  await row.getByRole("button", { name: "更改权限" }).click();
  await expect(page.getByLabel("所属学院", { exact: true })).toHaveValue("合成试用学院");
  await page.getByLabel("账号权限").selectOption("full");
  await page.getByRole("button", { name: "保存权限" }).click();
  await expect(row.getByText("全权限", { exact: true })).toBeVisible();
  await row.getByRole("button", { name: "更改权限" }).click();
  await page.getByLabel("账号权限").selectOption("ordinary");
  await page.getByRole("button", { name: "保存权限" }).click();
  await expect(row.getByText("普通", { exact: true })).toBeVisible();
  const memberContext = await browser.newContext();
  const member = await memberContext.newPage();
  await member.goto(page.url());
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
