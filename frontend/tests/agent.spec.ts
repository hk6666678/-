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
    answer: "当前授权范围的合成研究结果", evidence_links: [{ label: "来源", url: "/api/analyses/1" }], tool_result: {
      peer_outputs: { count: 4, peer_median: 5, peer_count: 23, sources: ["/api/patents/92/history"] },
      course_trend: { signal: "在控制限内", observations: [{ term: "2023秋", mean: 81, records: 5 }] },
    },
  }}));
  await page.getByRole("button", { name: "登录平台" }).click();
  await page.getByRole("button", { name: "目前系统多少学生？", exact: true }).click();
  await expect(page.getByLabel("问题", { exact: true })).toHaveValue("目前系统多少学生？");
  for (const question of ["看看课程通过情况", "再查科研成果"]) {
    await page.getByLabel("问题").fill(question);
    const field = page.getByLabel("问题", { exact: true });
    await field.dispatchEvent("keydown", { key: "Enter", isComposing: true });
    await expect(field).toHaveValue(question);
    await field.press("Shift+Enter");
    await expect(field).toHaveValue(question + "\n");
    await field.press("Enter");
    await expect(page.getByText(question, { exact: true })).toBeVisible();
  }
  await expect(page.getByRole("link", { name: "来源", exact: true })).toHaveCount(2);
  await page.getByText("查看计算依据", { exact: true }).first().click();
  await expect(page.getByText("与中位数相比少 1 项 · 比较范围 23 人").first()).toBeVisible();
  await expect(page.getByText("81 分", { exact: true }).first()).toBeVisible();
  await page.getByText("成果来源（1）").first().click();
  await expect(page.getByRole("link", { name: "专利记录 #92" })).toBeVisible();
});
