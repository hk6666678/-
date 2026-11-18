import { expect, test } from "@playwright/test";

test("one scope loads the cultivation stages and student evidence", async ({ page }) => {
  const scope = { college: "合成试用学院", major: "", grade: "2024" };
  const stages: string[] = [];
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
  await page.getByLabel("学生所在学院").selectOption(scope.college);
  await page.getByLabel("总览入学年份").fill(scope.grade);
  await page.getByRole("button", { name: "查看培养概况" }).click();
  await expect(page.getByRole("heading", { name: "培养概况" })).toBeVisible();
  expect(stages.sort()).toEqual(["courses", "midterm", "topic"]);
  await expect(page.getByText("通过率 100%")).toBeVisible();
  await expect(page.getByText("此范围操作未授权")).toBeVisible();
  await page.getByText("研究记录 42 · 1 条信号").click();
  await expect(page.getByText("中期未通过 · 分析 #3")).toBeVisible();
  await page.getByText("查看来源记录（1 条）").click();
  await expect(page.getByRole("link", { name: /记录 #7 v1/ }))
    .toHaveAttribute("href", "/api/records/midterm/7");
});
