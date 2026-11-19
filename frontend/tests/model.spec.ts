import { test, expect } from "@playwright/test";
test("model configuration is absent from the administration menu", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page
    .getByLabel("密码", { exact: true })
    .fill("Synthetic-password-123!");
  await page.getByRole("button", { name: "登录平台" }).click();
  await expect(page.getByRole("heading", { name: "今天想了解什么培养问题？" })).toBeVisible();
  await expect(page.getByRole("button", { name: "获准模型连接", exact: true })).toHaveCount(0);
});
