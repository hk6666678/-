import { expect, test } from "@playwright/test";

test("topic correlation submits a cohort and shows sample evidence", async ({ page }) => {
  await page.route("**/api/analyses/topic-correlation?*", (route) => {
    const query = new URL(route.request().url()).searchParams;
    expect(Object.fromEntries(query)).toEqual({
      college: "合成试用学院", major: "合成专业", entry_year: "2024", category: "patents",
    });
    return route.fulfill({ json: {
      cohort_count: 4, excluded: { 缺少有效选题实际日期: 1 }, uncertain_participations: 2,
      pearson_r: 1,
      points: [60, 70, 80].map((score, i) => ({
        research_id: `R${i + 1}`, score, output_count: i, topic_record_id: i + 1,
        output_ids: [3, 4].slice(0, i),
      })),
    }});
  });
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page.getByLabel("密码", { exact: true }).fill("Synthetic-password-123!");
  await page.getByRole("button", { name: "登录平台" }).click();
  await page.getByRole("button", { name: "培养过程分析", exact: true }).click();
  await page.getByText("选题分数与科研成果相关性", { exact: true }).click();
  await page.getByLabel("相关性分析学院").selectOption("合成试用学院");
  await page.getByLabel("相关性分析专业").fill("合成专业");
  await page.getByLabel("入学年份", { exact: true }).fill("2024");
  await page.getByLabel("相关性分析成果类别").selectOption("patents");
  await page.getByRole("button", { name: "计算相关性" }).click();
  await expect(page.getByText("有效样本 3/4 人。Pearson r 1.000。")).toBeVisible();
  await expect(page.getByRole("img", { name: "选题分数与选题后成果数散点图" })).toBeVisible();
  await page.getByText("样本与来源记录").click();
  await expect(page.getByText(/R3 · 80 分 · 选题记录 #3 · 选题后成果 2 项/)).toBeVisible();
});
