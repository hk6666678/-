import { expect, test } from "@playwright/test";

test("workbench shows current control limits and date-based reminders", async ({ page }) => {
  const courses = {
    id: 10, category: "courses", stale: false, scope: { college: "合成学院" },
    result: {},
    evidence: [80, 81, 80, 81, 80, 65].map((score, i) => ({
      student_id: 1,
      payload: {
        修读学期: `${2022 + Math.floor(i / 2)}${i % 2 ? "秋" : "春"}`,
        原始成绩: String(score),
        评分制度: "百分制",
      },
    })),
  };
  const topic = {
    id: 11, category: "topic", stale: false, scope: { college: "合成学院" },
    result: { reminders: [{ record_id: 2, overdue: true }, { record_id: 3, overdue: null }] },
    evidence: [],
  };
  await page.route("**/api/analyses", (route) => route.fulfill({
    json: { items: [{ ...courses, id: 12, stale: true }, topic, courses] },
  }));
  await page.route("**/api/analyses/10", (route) => route.fulfill({ json: courses }));
  await page.route("**/api/analyses/11", (route) => route.fulfill({ json: topic }));
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page.getByLabel("密码", { exact: true }).fill("Synthetic-password-123!");
  await page.getByRole("button", { name: "登录平台" }).click();
  await expect(page.getByText("课程控制图越界 1 人，可计算 1 人。")).toBeVisible();
  await expect(page.getByText("有明确日期依据的超期记录 1 条（记录 2）")).toBeVisible();
  await page.getByText("研究记录 1 · 低于下限").click();
  await expect(page.getByRole("img", { name: "百分制课程学期均分控制图" })).toBeVisible();
  await expect(page.getByText("下限 77.7 · 中心 80.4 · 上限 83.1")).toBeVisible();
  await page.getByRole("button", { name: "进入培养过程分析" }).click();
  await expect(page.getByRole("button", { name: "生成新分析版本" })).toBeVisible();
});
