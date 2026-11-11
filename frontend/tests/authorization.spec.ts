import { test, expect } from "@playwright/test";
test("grant scope, expose identity and revoke through UI", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page
    .getByLabel("密码", { exact: true })
    .fill("Synthetic-password-123!");
  await page.getByRole("button", { name: "登录平台" }).click();
  await page
    .getByRole("button", { name: "授权与脱敏验证", exact: true })
    .click();
  await page.getByLabel("配置账号").selectOption({ label: "synthetic-admin" });
  await page.getByRole("button", { name: "添加授权" }).click();
  await expect(page.getByRole("status")).toContainText("授权已保存");
  await page.getByRole("button", { name: "刷新合成记录" }).click();
  await expect(
    page.getByRole("cell", { name: "SYN-001", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("示例学生甲", { exact: true })).toHaveCount(0);
  await expect(
    page.getByRole("cell", { name: "SYN-002", exact: true }),
  ).toHaveCount(0);
  await page.getByLabel("操作权限").selectOption("identity");
  await page.getByRole("button", { name: "添加授权" }).click();
  await expect(page.getByRole("status")).toContainText("授权已保存");
  await page.getByRole("button", { name: "刷新合成记录" }).click();
  await expect(page.getByText("示例学生甲", { exact: true })).toBeVisible();
  await page
    .getByRole("row")
    .filter({ has: page.getByRole("cell", { name: "查看", exact: true }) })
    .getByRole("button", { name: "撤销" })
    .click();
  await expect(page.getByRole("status")).toContainText("授权已保存");
  await page.getByRole("button", { name: "刷新合成记录" }).click();
  await expect(page.getByRole("alert")).toContainText("没有示例记录");
  await expect(page.getByText("示例学生甲", { exact: true })).toHaveCount(0);
});
