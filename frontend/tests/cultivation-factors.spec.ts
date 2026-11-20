import { expect, test } from "@playwright/test";

test("cultivation factors runs directly and displays statistical results", async ({ page }) => {
  await page.route("**/api/cultivation/factors?*", (route) => {
    expect(Object.fromEntries(new URL(route.request().url()).searchParams)).toEqual({
      college: "合成试用学院", major: "合成专业", entry_year: "2024",
    });
    return route.fulfill({ json: {
      sample_size: 10, excluded: 2,
      factors: [{ factor: "选题成绩", coefficient: 0.3, interval: [0.1, 0.5], p_value: 0.02 }],
    }});
  });
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page.getByLabel("密码", { exact: true }).fill("Synthetic-password-123!");
  await page.getByRole("button", { name: "登录平台" }).click();
  await page.getByRole("button", { name: "培养影响因素", exact: true }).click();
  await page.getByLabel("学院", { exact: true }).selectOption("合成试用学院");
  await page.getByLabel("专业", { exact: true }).fill("合成专业");
  await page.getByLabel("入学年份", { exact: true }).fill("2024");
  await page.getByRole("button", { name: "分析影响因素" }).click();
  await expect(page.getByText("完整样本 10 人 · 排除 2 人")).toBeVisible();
  await expect(page.getByRole("row", { name: /选题成绩 0.300 0.100 至 0.500/ })).toBeVisible();
});
