import { expect, test } from "@playwright/test";

test("selecting a student loads their cultivation stages and evidence", async ({ page }) => {
  const scope = { college: "合成试用学院", major: "合成专业", student_id: 42 };
  const stages: string[] = [];
  await page.route("**/api/cultivation/students/42/signals", (route) => route.fulfill({ json: {
    blind_review: { batch: "合成送审批次", due: "2025-05-01", status: "未提交且已逾期" },
    mobility: { type: "转导师", date: "2025-06-01" },
    peer_outputs: { count: 0, peer_median: 2, peer_count: 4, below: true, sources: [] },
  }}));
  await page.route("**/api/students?limit=50&offset=0", (route) => route.fulfill({ json: {
    items: [{ id: 42, research_id: "R42", data: { 所属学院: scope.college, 专业: "合成专业" } }],
    total: 1,
  }}));
  await page.route(/\/api\/analyses\/(courses|topic|midterm)$/, (route) => {
    const category = new URL(route.request().url()).pathname.split("/").at(-1)!;
    expect(route.request().postDataJSON()).toEqual(scope);
    stages.push(category);
    if (category === "topic") return route.fulfill({ status: 403, json: { detail: "此范围操作未授权" } });
    const midterm = category === "midterm";
    return route.fulfill({ json: {
      id: midterm ? 3 : 1, category, scope, stale: false,
      result: { assessment_count: 1, student_count: 1, passed: midterm ? 0 : 1,
        failed: midterm ? 1 : 0, unknown: 0, pass_rate: midterm ? 0 : 100, reminders: [] },
      evidence: midterm ? [{ id: 7, student_id: 42, status: "不通过", version: 1,
        source: { batch_id: 8, source_department: "合成来源", sheet: "中期", row_number: 4 } }] : [],
    }});
  });
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page.getByLabel("密码", { exact: true }).fill("Synthetic-password-123!");
  await page.getByRole("button", { name: "登录平台" }).click();
  await page.getByRole("button", { name: "培养过程分析", exact: true }).click();
  await page.getByLabel("研究生", { exact: true }).selectOption("42");
  await page.getByRole("button", { name: "查看培养过程" }).click();
  await expect(page.getByRole("heading", { name: "个人培养过程" })).toBeVisible();
  await expect(page.locator("p").filter({ hasText: "R42 · 合成试用学院 · 合成专业" })).toBeVisible();
  await expect(page.getByRole("button", { name: "按范围查看" })).toHaveCount(0);
  expect(stages.sort()).toEqual(["courses", "midterm", "topic"]);
  await expect(page.getByText("通过率 100%")).toBeVisible();
  await page.route("**/api/cultivation/students/42/mentor-course-comparison", (route) => route.fulfill({ json: {
    has_group: true, as_of: "2026-11-19", items: [{
      college: "合成学院", course_code: "SYN-1", term: "2025秋", score: 90, peer_count: 3, peer_mean: 75, record_ids: [20],
    }],
  }}));
  await page.getByText("同导师组课程对比", { exact: true }).click();
  await expect(page.getByRole("row", { name: /SYN-1.*90.0.*75.0/ })).toBeVisible();
  await expect(page.getByText(/学籍异动 · 转导师/)).toBeVisible();
  await expect(page.getByText(/合成送审批次.*未提交且已逾期/)).toBeVisible();
  await expect(page.getByText(/低于同届中位数/)).toBeVisible();
  await expect(page.getByText("此范围操作未授权")).toBeVisible();
  await page.getByText("研究记录 42 · 1 条信号").click();
  await expect(page.getByText("中期未通过 · 分析 #3")).toBeVisible();
  await page.getByText("查看来源记录（1 条）").click();
  await expect(page.getByRole("link", { name: /记录 #7 v1/ }))
    .toHaveAttribute("href", "/api/records/midterm/7");
  await page.screenshot({ path: "test-results/cultivation-overview.png", fullPage: true });
});
