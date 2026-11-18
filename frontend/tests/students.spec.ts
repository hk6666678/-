import { execFileSync } from "node:child_process";
import { test, expect } from "@playwright/test";
test("basic Excel preview then confirmed archive", async ({ page }) => {
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
  const grants = ["maintain", "view", "identity"].map((operation) => ({
    category: "basic",
    operation,
    college: "合成学院",
    major: "合成专业",
  }));
  const given = await page.request.put(`/api/users/${session.user.id}/grants`, {
    headers: { "X-CSRF-Token": session.csrf_token },
    data: {
      expected_version: session.user.version,
      request_id: crypto.randomUUID(),
      grants,
    },
  });
  expect(given.status()).toBe(200);
  const template = await page.request.get("/api/templates/basic?sample=true");
  expect(template.status()).toBe(200);
  await page.getByRole("button", { name: "基础导入与学生档案" }).click();
  await page.getByText("筛选学生", { exact: true }).click();
  const majorFilter = page.getByLabel("专业筛选", { exact: true });
  expect(await majorFilter.locator("option").allTextContents()).toContain("计算机科学与技术");
  const yearFilter = page.getByLabel("入学年份筛选", { exact: true });
  const currentYear = await page.evaluate(() => new Date().getFullYear());
  expect(await yearFilter.locator("option").allTextContents()).toEqual([
    "全部年份",
    ...Array.from({ length: 10 }, (_, i) => String(currentYear - i)),
  ]);
  await page.getByText("导入学生档案", { exact: true }).click();
  await page.getByLabel("来源部门").fill("合成数据源");
  await page.getByLabel("基础信息 Excel").setInputFiles({
    name: "synthetic-basic.xlsx",
    mimeType:
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: execFileSync(
      "../.venv/Scripts/python.exe",
      [
        "-c",
        "import sys,io;from openpyxl import load_workbook;w=load_workbook(io.BytesIO(sys.stdin.buffer.read()));w.active.cell(3,1,'SYN-STUDENTS-ARCHIVE-ONLY');w.active.cell(3,2,'档案专项合成学生');o=io.BytesIO();w.save(o);sys.stdout.buffer.write(o.getvalue())",
      ],
      {
        input: await template.body(),
        env: { ...process.env, PYTHONUTF8: "1" },
      },
    ),
  });
  await page.getByRole("button", { name: "上传并预览" }).click();
  await expect(page.getByText("ready: 1 / invalid: 1")).toBeVisible();
  await page.getByRole("button", { name: "确认导入有效行" }).click();
  await expect(page.getByText(/imported: 1/)).toBeVisible();
  await page.getByLabel("专业筛选", { exact: true }).selectOption("合成专业");
  await page.getByLabel("入学年份筛选", { exact: true }).selectOption("2025");
  await page.getByLabel("培养层次筛选", { exact: true }).selectOption("硕士");
  await page.getByRole("button", { name: "查询学生档案" }).click();
  await expect(
    page.getByRole("button", { name: "查看来源" }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "查看来源" }).first().click();
  await expect(page.locator("pre")).toContainText("original_row");
});
