import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
const python = "D:/AQP-PGS/.venv/Scripts/python.exe";
const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const scope = { college: "规模合成学院", major: "规模合成专业" };

test("mentor group research shows scale against output and explains missing labels", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page.getByLabel("密码", { exact: true }).fill("Synthetic-password-123!");
  await page.getByRole("button", { name: "登录平台" }).click();
  await expect(page.getByRole("heading", { name: "Agent 智能问答" })).toBeVisible();
  const session = await (await page.request.get("/api/me")).json();
  const headers = { "X-CSRF-Token": session.csrf_token };
  const originalGrants = await (await page.request.get("/api/access/grants")).json();
  try {
    const grants = ["basic", "mentor_groups", "courses", "topic", "midterm", "research_papers", "patents", "awards", "conferences", "papers"].flatMap((category) =>
      ["maintain", "view", "identity", "analyze", "labels"].map((operation) => ({ category, operation, ...scope })));
    expect((await page.request.put(`/api/users/${session.user.id}/grants`, {
      headers, data: { expected_version: session.user.version, request_id: crypto.randomUUID(), grants },
    })).status()).toBe(200);

    const workbook = (marker: string, header: string[], rows: (string | number)[][]) => execFileSync(python, ["-c",
      `import sys,io;from openpyxl import Workbook;w=Workbook();s=w.active;s.append(${JSON.stringify(marker)});s.append(${JSON.stringify(header)});${rows.map((row) => `s.append(${JSON.stringify(row)});`).join("")}o=io.BytesIO();w.save(o);sys.stdout.buffer.write(o.getvalue())`]);
    const basic = await (await page.request.post("/api/imports/basic/preview", { headers, multipart: { source_department: "合成来源", file: { name: "basic.xlsx", mimeType: XLSX,
      buffer: workbook(["AQP-PGS", "basic", "1"], ["学号", "姓名", "所属学院", "专业", "培养层次", "入学年份"],
        [1, 2, 3].map((n) => [`SCALE-${n}`, `规模学生${n}`, scope.college, scope.major, "硕士", "2024"])) } } })).json();
    expect((await page.request.post(`/api/imports/${basic.id}/confirm`, { headers })).status()).toBe(200);
    const students = (await (await page.request.get("/api/students?limit=200")).json()).items
      .filter((s: { data: { 所属学院: string } }) => s.data["所属学院"] === scope.college);
    const directory = async (kind: string, number: string) => (await page.request.post(`/api/mentor-groups/directory/${kind}`, {
      headers, data: { number, name: `规模${kind === "mentors" ? "导师" : "课题组"}${number.slice(-1)}`, ...scope },
    })).json();
    const group = await directory("groups", "SCALE-G1");
    const small = await directory("mentors", "SCALE-M1");
    const large = await directory("mentors", "SCALE-M2");
    for (const [student, mentor] of [[students[0], small], [students[1], large], [students[2], large]]) {
      expect((await page.request.post("/api/mentor-groups/relations", { headers, data: {
        student_id: student.id, mentor_id: mentor.id, group_id: group.id, start_date: "2024-09-01",
        source_department: "合成来源", reason: "合成关系",
      } })).status()).toBe(200);
    }
    // 人均成果：学生1 一篇；学生2、3 共五篇
    const papers = [1, 2, 2, 3, 3, 3].map((n, index) => [`SCALE-P-${index}`, "合成论文", `SCALE-${n}`, `规模学生${n}`, 1, "第一作者", scope.college, scope.major, 2025]);
    const preview = await (await page.request.post("/api/research-outputs/preview", { headers, multipart: { source_department: "合成来源", file: { name: "papers.xlsx", mimeType: XLSX,
      buffer: workbook(["AQP-PGS", "research_papers", "1"], ["业务编号/DOI", "论文标题", "学号", "姓名", "作者次序", "参与角色", "所属学院", "专业", "发表年份"], papers) } } })).json();
    const imported = await page.request.post(`/api/research-outputs/previews/${preview.id}/confirm`, { headers, data: { accept_changes: true } });
    expect(imported.status()).toBe(200);

    await page.getByRole("button", { name: "导师与课题组数据", exact: true }).click();
    await page.getByText("规模与产出：团队大小和人均成果的关系", { exact: true }).click();
    await page.getByRole("button", { name: "分析规模与产出", exact: true }).click();
    const scale = page.getByRole("region", { name: "规模与产出结果" });
    await expect(scale.getByText("纳入 2 位导师。")).toBeVisible();
    // 两个单位不足以说明关系，按设计不计算相关系数
    await expect(scale.getByText("可比较的单位不足三个，不计算相关系数。")).toBeVisible();
    await expect(scale.getByRole("row", { name: "规模导师1 1 1.00" })).toBeVisible();
    await expect(scale.getByRole("row", { name: "规模导师2 2 2.50" })).toBeVisible();

    // 补第三位导师（1 名学生、2 篇论文）：x=[1,2,1]，y=[1,2.5,2]，r≈0.756
    const fourth = await (await page.request.post("/api/imports/basic/preview", { headers, multipart: { source_department: "合成来源", file: { name: "basic4.xlsx", mimeType: XLSX,
      buffer: workbook(["AQP-PGS", "basic", "1"], ["学号", "姓名", "所属学院", "专业", "培养层次", "入学年份"],
        [["SCALE-4", "规模学生4", scope.college, scope.major, "硕士", "2024"]]) } } })).json();
    expect((await page.request.post(`/api/imports/${fourth.id}/confirm`, { headers })).status()).toBe(200);
    const student4 = (await (await page.request.get("/api/students?limit=200")).json()).items
      .find((s: { data: { 学号: string } }) => s.data["学号"] === "SCALE-4");
    const third = await directory("mentors", "SCALE-M3");
    expect((await page.request.post("/api/mentor-groups/relations", { headers, data: {
      student_id: student4.id, mentor_id: third.id, group_id: group.id, start_date: "2024-09-01",
      source_department: "合成来源", reason: "合成关系",
    } })).status()).toBe(200);
    const more = await (await page.request.post("/api/research-outputs/preview", { headers, multipart: { source_department: "合成来源", file: { name: "papers4.xlsx", mimeType: XLSX,
      buffer: workbook(["AQP-PGS", "research_papers", "1"], ["业务编号/DOI", "论文标题", "学号", "姓名", "作者次序", "参与角色", "所属学院", "专业", "发表年份"],
        ["SCALE-P-6", "SCALE-P-7"].map((key) => [key, "合成论文", "SCALE-4", "规模学生4", 1, "第一作者", scope.college, scope.major, 2025])) } } })).json();
    expect((await page.request.post(`/api/research-outputs/previews/${more.id}/confirm`, { headers, data: { accept_changes: true } })).status()).toBe(200);
    await page.getByRole("button", { name: "分析规模与产出", exact: true }).click();
    await expect(scale.getByText("纳入 3 位导师。")).toBeVisible();
    await expect(scale.getByText(/相关系数 r = 0\.756（3 个单位）。/)).toBeVisible();
    await expect(scale.getByText(/单位数量较少/)).toBeVisible();
    await expect(scale.getByRole("row", { name: "规模导师3 1 2.00" })).toBeVisible();

    await page.getByText("成长路径：优秀论文学生与其他学生的差别", { exact: true }).click();
    await page.getByLabel("成长路径单位", { exact: true }).selectOption(String(small.id));
    await page.getByRole("button", { name: "比较成长路径", exact: true }).click();
    const growth = page.getByRole("region", { name: "成长路径结果" });
    await expect(growth.getByText(/历届学生 1 人 · 优秀组 0 人 · 对照组 0 人 · 未标注或待评 1 人/)).toBeVisible();
    await expect(growth.getByText(/尚无专家样本标签/)).toBeVisible();
    // 样本不足时不显示差别一栏
    await expect(growth.getByRole("columnheader", { name: "差别" })).toHaveCount(0);
  } finally {
    const latest = await (await page.request.get("/api/me")).json();
    await page.request.put(`/api/users/${latest.user.id}/grants`, { headers, data: { expected_version: latest.user.version, request_id: crypto.randomUUID(), grants: originalGrants } });
  }
});
