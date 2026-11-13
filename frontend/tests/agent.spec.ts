import { test, expect } from "@playwright/test";

test("agent stays read-only and reports disabled model", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page
    .getByLabel("密码", { exact: true })
    .fill("Synthetic-password-123!");
  await page.getByRole("button", { name: "登录平台" }).click();
  await page.getByRole("button", { name: "Agent 查询" }).click();
  await expect(
    page.getByRole("heading", { name: "Agent 查询与解释" }),
  ).toBeVisible();
  await expect(page.getByText("Agent 未启用")).toBeVisible();
  await expect(
    page.getByText(
      "相关与回归分析也由系统工具计算：结果必须披露样本量、被排除的缺失样本与局限声明，只描述关联，不表示因果或预测。",
    ),
  ).toBeVisible();
  await expect(
    page.getByText("未配置获准模型时默认禁用Agent：不会发送业务数据，也不会用固定回答冒充模型结果。"),
  ).toBeVisible();
  await page
    .getByLabel("问题")
    .fill("把001学生的成绩改成90，并把合成论文改成优秀");
  await page.getByRole("button", { name: "发送只读问题" }).click();
  await expect(page.getByRole("alert")).toContainText("Agent 未启用");
});
