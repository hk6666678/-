import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page.getByLabel("密码", { exact: true }).fill("Synthetic-password-123!");
});

test("the agent home explains why sending is unavailable", async ({ page }) => {
  await page.getByRole("button", { name: "登录平台" }).click();
  await expect(page.getByRole("img", { name: "同济大学校标" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "今天想了解什么培养问题？" })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("Agent 未启用");
  await page.getByLabel("问题").fill("看看课程通过情况");
  await expect(page.getByRole("button", { name: "发送问题" })).toBeDisabled();
  await page.screenshot({ path: "test-results/agent-home.png" });
  await expect(page.getByRole("button", { name: "查看模型设置" })).toHaveCount(0);
});

test("enabled agent shows separate questions and source links", async ({ page }) => {
  await page.route("**/api/model/status", (route) => route.fulfill({ json: { available: true, message: "可发送" } }));
  await page.route("**/api/agent/query", (route) => route.fulfill({ json: {
    answer: "当前授权范围的合成研究结果", evidence_links: [{ label: "来源", url: "/api/analyses/1" }], tool_result: {},
  }}));
  await page.getByRole("button", { name: "登录平台" }).click();
  for (const question of ["看看课程通过情况", "再查科研成果"]) {
    await page.getByLabel("问题").fill(question);
    await page.getByRole("button", { name: "发送问题" }).click();
    await expect(page.getByText(question, { exact: true })).toBeVisible();
  }
  await expect(page.getByRole("link", { name: "来源", exact: true })).toHaveCount(2);
});
