import { test, expect } from "@playwright/test";
test("administrator filters management audit", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page
    .getByLabel("密码", { exact: true })
    .fill("Synthetic-password-123!");
  await page.getByRole("button", { name: "登录平台" }).click();
  await page.getByRole("button", { name: "审计查询", exact: true }).click();
  await page.getByLabel("操作名称").fill("login");
  await page.getByRole("button", { name: "查询审计", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("共");
  await expect(
    page.getByRole("row").filter({ hasText: "login" }).first(),
  ).toBeVisible();
  await page.getByLabel("操作名称").fill("nonexistent");
  await page.getByRole("button", { name: "查询审计", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("共 0 条");
});
