import { test, expect } from "@playwright/test";
test("model stays disabled without approved configuration", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page
    .getByLabel("密码", { exact: true })
    .fill("Synthetic-password-123!");
  await page.getByRole("button", { name: "登录平台" }).click();
  await page.getByRole("button", { name: "获准模型连接", exact: true }).click();
  await expect(page.getByLabel("启用模型", { exact: true })).not.toBeChecked();
  await page.getByRole("button", { name: "保存模型配置" }).click();
  await expect(page.getByRole("status")).toContainText("配置已保存");
  await page.getByRole("button", { name: "检验已保存连接" }).click();
  await expect(page.getByRole("alert")).toContainText("未启用");
});
