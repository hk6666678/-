import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
const python = "D:/AQP-PGS/.venv/Scripts/python.exe";
const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

test("data consistency checks list mismatches and the data classification", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page.getByLabel("密码", { exact: true }).fill("Synthetic-password-123!");
  await page.getByRole("button", { name: "登录平台" }).click();
  await expect(page.getByRole("heading", { name: "Agent 智能问答" })).toBeVisible();
  const session = await (await page.request.get("/api/me")).json();
  const headers = { "X-CSRF-Token": session.csrf_token };
  const originalGrants = await (await page.request.get("/api/access/grants")).json();
  const scope = { college: "核对合成学院", major: "核对合成专业" };
  try {
    const grants = ["basic", "courses", "topic", "midterm", "papers", "mentor_groups"].flatMap((category) =>
      ["maintain", "view", "identity", "analyze"].map((operation) => ({ category, operation, ...scope })));
    expect((await page.request.put(`/api/users/${session.user.id}/grants`, {
      headers, data: { expected_version: session.user.version, request_id: crypto.randomUUID(), grants },
    })).status()).toBe(200);
    // 一名学生登记了异动类型却没有异动时间；另一名学生没有差异
    const basic = execFileSync(python, ["-c",
      `import sys,io;from openpyxl import Workbook;w=Workbook();s=w.active;s.append(['AQP-PGS','basic','1']);s.append(['学号','姓名','所属学院','专业','培养层次','入学年份','学籍异动类型','学籍异动时间']);s.append(['QA-1','核对学生一','${scope.college}','${scope.major}','硕士','2024','转导师','']);s.append(['QA-2','核对学生二','${scope.college}','${scope.major}','硕士','2024','','']);o=io.BytesIO();w.save(o);sys.stdout.buffer.write(o.getvalue())`]);
    const preview = await (await page.request.post("/api/imports/basic/preview", { headers, multipart: { source_department: "合成来源", file: { name: "basic.xlsx", mimeType: XLSX, buffer: basic } } })).json();
    expect((await page.request.post(`/api/imports/${preview.id}/confirm`, { headers })).status()).toBe(200);

    await page.getByRole("button", { name: "数据纠错与维护", exact: true }).click();
    const panel = page.getByRole("region", { name: "数据一致性核对", exact: true });
    await expect(panel).toBeVisible();
    await panel.getByLabel("核对学院", { exact: true }).selectOption("__other_college__");
    await panel.getByLabel("其他学院名称", { exact: true }).fill(scope.college);
    await panel.getByLabel("核对专业", { exact: true }).fill(scope.major);
    await panel.getByRole("button", { name: "开始核对", exact: true }).click();
    const result = panel.getByRole("region", { name: "核对结果", exact: true });
    await expect(result.getByText(/共核对 2 名在册学生 · 有 1 项发现差异/)).toBeVisible();
    const mobility = result.getByRole("row", { name: /学籍异动类型与异动时间缺少其中一项/ });
    await expect(mobility.getByRole("cell", { name: "涉及 1 名学生" })).toBeVisible();
    await mobility.getByText("查看 1 名学生", { exact: true }).click();
    await expect(mobility.getByRole("listitem")).toHaveCount(1);
    await expect(mobility.getByText(/已填类型/)).toBeVisible();
    // 其余九项检查未发现差异，待关联记录一项为空；身份信息不出现在明细里
    await expect(result.getByRole("cell", { name: "未发现差异", exact: true })).toHaveCount(9);
    await expect(result.getByRole("row", { name: /尚未关联到正式学生档案/ }).getByRole("cell", { name: "没有待关联记录" })).toBeVisible();
    await expect(result.getByText("核对学生一")).toHaveCount(0);

    // 数据分级：三级及保护方式
    const levels = page.locator("details.card", { has: page.getByText("数据分级", { exact: true }) });
    await expect(levels.getByText("公开", { exact: true })).toBeVisible();
    await expect(levels.getByText("敏感", { exact: true })).toBeVisible();
    await expect(levels.getByText("学生姓名与学号", { exact: true })).toBeVisible();
    await expect(levels.getByText(/建议映射，待业务确认/)).toBeVisible();
  } finally {
    const latest = await (await page.request.get("/api/me")).json();
    await page.request.put(`/api/users/${latest.user.id}/grants`, { headers, data: { expected_version: latest.user.version, request_id: crypto.randomUUID(), grants: originalGrants } });
  }
});
