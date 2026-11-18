import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";

test("course analysis preserves source evidence and immutable stale history", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page
    .getByLabel("密码", { exact: true })
    .fill("Synthetic-password-123!");
  await page.getByRole("button", { name: "登录平台" }).click();
  await expect(
    page.getByRole("heading", { name: "Agent 智能问答" }),
  ).toBeVisible();
  const session = await (await page.request.get("/api/me")).json();
  const headers = { "X-CSRF-Token": session.csrf_token };
  const original = (
    await (
      await page.request.get(`/api/users/${session.user.id}/grants`)
    ).json()
  ).grants;
  async function grants(values: unknown) {
    const me = await (await page.request.get("/api/me")).json();
    return page.request.put(`/api/users/${session.user.id}/grants`, {
      headers,
      data: {
        expected_version: me.user.version,
        request_id: crypto.randomUUID(),
        grants: values,
      },
    });
  }
  try {
    expect(
      (
        await grants(
          ["basic", "courses"].flatMap((category) =>
            ["maintain", "view", "analyze", "pass_rules", "void"].map(
              (operation) => ({
                category,
                operation,
                college: "课程08合成学院",
                major: "课程08合成专业",
              }),
            ),
          ),
        )
      ).status(),
    ).toBe(200);
    const bytes = execFileSync(
      "../.venv/Scripts/python.exe",
      [
        "-c",
        "import sys,io;from openpyxl import Workbook;w=Workbook();s=w.active;s.append(['AQP-PGS','basic','1']);s.append(['学号','姓名','所属学院','专业','培养层次','入学年份']);s.append(['SYN-ANALYSIS-08','课程合成学生','课程08合成学院','课程08合成专业','硕士','2025']);o=io.BytesIO();w.save(o);sys.stdout.buffer.write(o.getvalue())",
      ],
      { env: { ...process.env, PYTHONUTF8: "1" } },
    );
    const basic = await (
      await page.request.post("/api/imports/basic/preview", {
        headers,
        multipart: {
          source_department: "课程08合成来源",
          file: {
            name: "synthetic.xlsx",
            mimeType:
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            buffer: bytes,
          },
        },
      })
    ).json();
    expect(
      (
        await page.request.post(`/api/imports/${basic.id}/confirm`, { headers })
      ).status(),
    ).toBe(200);
    const courses = execFileSync(
      "../.venv/Scripts/python.exe",
      [
        "-c",
        "import sys,io;from openpyxl import Workbook;w=Workbook();s=w.active;s.append(['AQP-PGS','courses','1']);s.append(['学号','姓名','课程编号','课程名称','修读学期','考核次数','评分制度','原始成绩','业务通过结果','所属学院','专业']);[s.append(['SYN-ANALYSIS-08','课程合成学生','SYN-C08','合成课程','2025秋',i+1,'百分制','' if i>5 else 80,v,'课程08合成学院','课程08合成专业']) for i,v in enumerate(['通过']*4+['不通过']*2+['',''])];o=io.BytesIO();w.save(o);sys.stdout.buffer.write(o.getvalue())",
      ],
      { env: { ...process.env, PYTHONUTF8: "1" } },
    );
    const batch = await (
      await page.request.post("/api/imports/courses/preview", {
        headers,
        multipart: {
          source_department: "课程08合成来源",
          file: {
            name: "synthetic.xlsx",
            mimeType:
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            buffer: courses,
          },
        },
      })
    ).json();
    expect(
      (
        await page.request.post(`/api/imports/courses/${batch.id}/confirm`, {
          headers,
        })
      ).status(),
    ).toBe(200);
    await page
      .getByRole("button", { name: "培养过程分析", exact: true })
      .click();
    await page.getByLabel("研究生", { exact: true }).selectOption({ index: 1 });
    await page.getByRole("button", { name: "查看培养过程", exact: true }).click();
    await page.getByRole("button", { name: "查看课程明细" }).click();
    await expect(page.getByText(/考核记录 8 · 去重学生 1/)).toContainText(
      "通过率 66.67%",
    );
    await expect(
      page.getByRole("cell", { name: "66.67%", exact: true }),
    ).toBeVisible();
    await expect(page.locator("meter")).toHaveCount(2);
    await page.getByText("来源下钻与逐条证据", { exact: true }).click();
    await expect(
      page.getByRole("link", { name: "记录版本和来源历史" }),
    ).toHaveCount(8);
    const snapshots = await (await page.request.get("/api/analyses")).json();
    const oldId = snapshots.items.find((item: { category: string }) => item.category === "courses").id;
    await page
      .getByRole("button", { name: "业务规则管理", exact: true })
      .click();
  await page.getByText("课程通过与培养要求", { exact: true }).click();
    const passRules = page.locator("article.card", {
      has: page.getByRole("heading", {
        name: "课程通过规则与培养要求",
        exact: true,
      }),
    });
    await passRules
      .getByLabel("规则环节", { exact: true })
      .selectOption("courses");
    await passRules
      .getByLabel("学院", { exact: true })
      .selectOption("__other_college__");
    await passRules
      .getByLabel("其他学院名称", { exact: true })
      .fill("课程08合成学院");
    await passRules
      .getByLabel("专业（须具体专业）", { exact: true })
      .fill("课程08合成专业");
    await passRules.getByLabel("课程编号", { exact: true }).fill("SYN-C08");
    await passRules.getByLabel("最低通过分数").fill("70");
    await passRules
      .getByLabel("业务确认依据")
      .fill("合成业务确认通过线70");
    await passRules
      .getByLabel("业务人员已确认适用范围及规则")
      .check();
    await passRules
      .getByRole("button", { name: "确认新规则版本" })
      .click();
    await expect(
      passRules.locator("pre").filter({ hasText: "version" }).first(),
    ).toBeVisible();
    // Simulate an immutable pre-09 snapshot without the optional progress field.
    const old = await (await page.request.get(`/api/analyses/${oldId}`)).json();
    expect(old.stale).toBe(true);
    expect(old.result.pass_rate).toBe(66.67);
    expect(
      (await page.request.get(`/api/analyses/${oldId}/export`)).status(),
    ).toBe(403);
    await page.screenshot({
      path: "test-results/course-analysis.png",
      fullPage: true,
    });
    expect((await grants([])).status()).toBe(200);
    expect((await page.request.get(`/api/analyses/${oldId}`)).status()).toBe(
      403,
    );
  } finally {
    expect((await grants(original)).status()).toBe(200);
  }
});
