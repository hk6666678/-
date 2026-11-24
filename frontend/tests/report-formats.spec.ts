import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

const python = "D:/AQP-PGS/.venv/Scripts/python.exe";
const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const scope = { college: "格式合成学院", major: "格式合成专业" };

test("reports download as Excel, PDF or Word according to the chosen format", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page.getByLabel("密码", { exact: true }).fill("Synthetic-password-123!");
  await page.getByRole("button", { name: "登录平台" }).click();
  await expect(page.getByRole("heading", { name: "Agent 智能问答" })).toBeVisible();
  const session = await (await page.request.get("/api/me")).json();
  const headers = { "X-CSRF-Token": session.csrf_token };
  const originalGrants = await (await page.request.get("/api/access/grants")).json();
  const setGrants = async (operations: string[]) => {
    const me = await (await page.request.get("/api/me")).json();
    expect((await page.request.put(`/api/users/${me.user.id}/grants`, {
      headers,
      data: {
        expected_version: me.user.version,
        request_id: crypto.randomUUID(),
        grants: operations.map((operation) => ({ category: "basic", operation, ...scope })),
      },
    })).status()).toBe(200);
  };
  try {
    await setGrants(["maintain", "view", "identity", "analyze", "export"]);
    const basic = execFileSync(python, ["-c",
      `import sys,io;from openpyxl import Workbook;w=Workbook();s=w.active;s.append(['AQP-PGS','basic','1']);s.append(['学号','姓名','所属学院','专业','培养层次','入学年份']);s.append(['FORMAT-1','格式合成学生','${scope.college}','${scope.major}','硕士','2024']);o=io.BytesIO();w.save(o);sys.stdout.buffer.write(o.getvalue())`]);
    const preview = await (await page.request.post("/api/imports/basic/preview", { headers, multipart: { source_department: "合成来源", file: { name: "basic.xlsx", mimeType: XLSX, buffer: basic } } })).json();
    expect((await page.request.post(`/api/imports/${preview.id}/confirm`, { headers })).status()).toBe(200);
    const studentId = (await (await page.request.get("/api/students?limit=200")).json()).items
      .find((s: { data: { 学号: string } }) => s.data["学号"] === "FORMAT-1").id;

    await page.getByRole("button", { name: "三级报告", exact: true }).click();
    // 学生筛选默认收起，先展开
    await page.getByText("按专业缩小学生列表", { exact: true }).click();
    await page.getByLabel("学生列表专业筛选", { exact: true }).selectOption(scope.major);
    await page.getByLabel("学生研究编号", { exact: true }).selectOption(String(studentId));
    await page.getByRole("button", { name: "查看学生报告", exact: true }).click();
    const exportButton = page.getByRole("button", { name: "导出学生报告（需独立导出授权）", exact: true });
    await expect(exportButton).toBeVisible();
    const formatPicker = page.getByLabel("导出格式", { exact: true });
    await expect(formatPicker).toHaveValue("xlsx");

    let downloads = 0;
    page.on("download", () => { downloads += 1; });
    const ZIP_MAGIC = Buffer.from([0x50, 0x4b, 0x03, 0x04]);
    const save = async () => {
      const [download] = await Promise.all([page.waitForEvent("download"), exportButton.click()]);
      const magic = readFileSync((await download.path())!).subarray(0, 5);
      return { name: download.suggestedFilename(), magic };
    };

    // Excel 仍是默认，请求地址不变
    const excel = await save();
    expect(excel.name).toBe(`report-student-${studentId}.xlsx`);
    expect(excel.magic.subarray(0, 4).equals(ZIP_MAGIC)).toBe(true);

    await formatPicker.selectOption("pdf");
    const pdf = await save();
    expect(pdf.name).toBe(`report-student-${studentId}.pdf`);
    expect(pdf.magic.toString("latin1")).toBe("%PDF-");

    await formatPicker.selectOption("docx");
    const word = await save();
    expect(word.name).toBe(`report-student-${studentId}.docx`);
    expect(word.magic.subarray(0, 4).equals(ZIP_MAGIC)).toBe(true);

    // 排版文档与 Excel 走同一道导出授权：撤掉后不会产生下载，页面说明原因
    await setGrants(["maintain", "view", "identity", "analyze"]);
    await formatPicker.selectOption("pdf");
    await exportButton.click();
    await expect(page.getByRole("alert")).toContainText(/授权/);
    await page.waitForTimeout(500);
    expect(downloads).toBe(3);
  } finally {
    const latest = await (await page.request.get("/api/me")).json();
    await page.request.put(`/api/users/${latest.user.id}/grants`, { headers, data: { expected_version: latest.user.version, request_id: crypto.randomUUID(), grants: originalGrants } });
  }
});
