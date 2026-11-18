import { execFileSync } from "node:child_process";
import { test, expect } from "@playwright/test";
test("three-level reports with charts drilldown and authorized export", async ({
  page,
}) => {
  test.setTimeout(90000);
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
  expect(
    (
      await page.request.put(`/api/users/${session.user.id}/grants`, {
        headers,
        data: {
          expected_version: session.user.version,
          request_id: crypto.randomUUID(),
          grants: [
            ...["basic", "patents", "mentor_groups"].flatMap((category) =>
              ["maintain", "view", "identity", "analyze", "export"].map(
                (operation) => ({
                  category,
                  operation,
                  college: "合成学院",
                  major: "合成专业",
                }),
              ),
            ),
            ...["view", "analyze"].map((operation) => ({
              category: "talent_evaluation",
              operation,
              college: "合成学院",
              major: "合成专业",
            })),
          ],
        },
      })
    ).status(),
  ).toBe(200);
  await page.getByRole("button", { name: "基础导入与学生档案" }).click();
  const template = await page.request.get("/api/templates/basic?sample=true");
  await page.getByText("导入学生档案", { exact: true }).click();
  await page.getByLabel("来源部门", { exact: true }).fill("报告专项合成数据源");
  await page.getByLabel("基础信息 Excel", { exact: true }).setInputFiles({
    name: "synthetic-basic.xlsx",
    mimeType:
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: execFileSync(
      "../.venv/Scripts/python.exe",
      [
        "-c",
        "import sys,io;from openpyxl import load_workbook;w=load_workbook(io.BytesIO(sys.stdin.buffer.read()));w.active.cell(3,1,'SYN-REPORT-0001');w.active.cell(3,2,'专项报告合成学生');o=io.BytesIO();w.save(o);sys.stdout.buffer.write(o.getvalue())",
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
  await page.getByRole("button", { name: "科研成果导入", exact: true }).click();
  await page.getByRole("tab", { name: "专利", exact: true }).click();
  await page.getByText("导入专利", { exact: true }).click();
  await page.getByLabel("来源部门", { exact: true }).fill("报告专项合成专利科");
  await page.getByLabel("标准 Excel 文件", { exact: true }).setInputFiles({
    name: "synthetic-patents.xlsx",
    mimeType:
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: execFileSync(
      "../.venv/Scripts/python.exe",
      [
        "-c",
        "import sys,io;from openpyxl import Workbook;w=Workbook();a=w.active;a.append(['AQP-PGS','patents','1']);a.append(['申请号','专利名称','学号','姓名','作者次序','参与角色','所属学院','专业','专利类型','申请日期']);a.append(['PAT-REPORT-0001','合成报告专利','SYN-REPORT-0001','专项报告合成学生',1,'第一作者','合成学院','合成专业','发明','2026-03-01']);o=io.BytesIO();w.save(o);sys.stdout.buffer.write(o.getvalue())",
      ],
      { env: { ...process.env, PYTHONUTF8: "1" } },
    ),
  });
  await page.getByRole("button", { name: "预览导入", exact: true }).click();
  await page.getByRole("button", { name: "确认导入", exact: true }).click();
  await expect(
    page.getByRole("cell", { name: "专项报告合成学生", exact: false }),
  ).toBeVisible();
  const roster = await (
    await page.request.get(
      `/api/students?limit=200&offset=0&major=${encodeURIComponent("合成专业")}`,
    )
  ).json();
  const mine = roster.items.find(
    (item: { student_number?: string }) =>
      item.student_number === "SYN-REPORT-0001",
  );
  if (!mine) throw new Error("report student missing from roster");
  const mentor = await (
    await page.request.post("/api/mentor-groups/directory/mentors", {
      headers,
      data: {
        number: "SYN-REPORT-MENTOR",
        name: "报告专项合成导师",
        college: "合成学院",
        major: "合成专业",
      },
    })
  ).json();
  const group = await (
    await page.request.post("/api/mentor-groups/directory/groups", {
      headers,
      data: {
        number: "SYN-REPORT-GROUP",
        name: "报告专项合成课题组",
        college: "合成学院",
        major: "合成专业",
      },
    })
  ).json();
  expect(
    (
      await page.request.post("/api/mentor-groups/relations", {
        headers,
        data: {
          student_id: mine.id,
          mentor_id: mentor.id,
          group_id: group.id,
          start_date: "2025-09-01",
          source_department: "报告专项合成培养办",
          reason: "报告专项合成关系",
        },
      })
    ).status(),
  ).toBe(200);
  await page.getByRole("button", { name: "三级报告", exact: true }).click();
  await page.getByText("按专业缩小学生列表", { exact: true }).click();
  await page
    .getByLabel("学生列表专业筛选", { exact: true })
    .selectOption("合成专业");
  await page
    .getByLabel("学生研究编号", { exact: true })
    .selectOption(String(mine.id));
  await page.getByRole("button", { name: "查看学生报告" }).click();
  await expect(
    page.getByText(/SYN-REPORT-0001 专项报告合成学生/),
  ).toBeVisible();
  await expect(page.getByText("缺失：尚无评分快照，不填零。").first()).toBeVisible();
  await expect(
    page.getByText("当前授权不足，该段未纳入。").first(),
  ).toBeVisible();
  await expect(
    page.locator("svg[aria-label='项柱状图']").first(),
  ).toBeVisible();
  await expect(
    page.locator("svg[aria-label='项柱状图'] text", { hasText: "2026" }).first(),
  ).toBeVisible();
  const studentDownload = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "导出学生报告（需独立导出授权）" })
    .click();
  expect((await studentDownload).suggestedFilename()).toBe(
    `report-student-${mine.id}.xlsx`,
  );
  await page.getByText("导师课题组报告", { exact: true }).click();
  await page
    .getByLabel("导师（可空，进入本页自动读取目录）", { exact: true })
    .selectOption(String(mentor.id));
  await page.getByRole("button", { name: "查看课题组报告" }).click();
  await expect(
    page.getByText(`统计日期 ${new Date().toISOString().slice(0, 10)} · 当前授权范围内学生1人`),
  ).toBeVisible();
  await expect(page.getByText("成果去重1项，参与学生1人").first()).toBeVisible();
  await expect(page.getByText(/毕业：缺少已确认的毕业口径/)).toBeVisible();
  const groupDownload = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "导出课题组报告（需独立导出授权）" })
    .click();
  expect((await groupDownload).suggestedFilename()).toBe(
    `report-group-${mentor.id}.xlsx`,
  );
  await page.getByText("学院学科报告", { exact: true }).click();
  await page.getByLabel("学院", { exact: true }).selectOption("__other_college__");
  await page.getByLabel("其他学院名称", { exact: true }).fill("合成学院");
  await page.getByLabel("专业", { exact: true }).fill("合成专业");
  await page.getByRole("button", { name: "查看学院报告" }).click();
  await expect(page.getByText(/当前授权可见\d+人/).first()).toBeVisible();
  await expect(
    page.getByText(/成果去重\d+项，个人参与\d+人次/).first(),
  ).toBeVisible();
  const collegeDownload = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "导出学院报告（需独立导出授权）" })
    .click();
  expect((await collegeDownload).suggestedFilename()).toBe("report-college.xlsx");
  await page
    .locator("article.card", {
      has: page.getByRole("heading", { name: "学生发展报告" }),
    })
    .screenshot({ path: "../artifacts/full08-student-report.png" });
  await page.setViewportSize({ width: 550, height: 1200 });
  const columns = await page
    .locator(".report-charts")
    .first()
    .evaluate(
      (el) => getComputedStyle(el).gridTemplateColumns.split(" ").length,
    );
  expect(columns).toBe(1);
  await page.setViewportSize({ width: 1280, height: 1000 });
  await page.locator(".content").evaluate((el) => el.scrollTo(0, 0));
  await page.screenshot({
    path: "../artifacts/full08-reports.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1280, height: 1000 });
  await page.locator(".content").evaluate(el => el.scrollTo(0, 0));
  await page.screenshot({ path: "../artifacts/ui-polish/reports-desktop.png" });
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(375);
  await page.screenshot({ path: "../artifacts/ui-polish/reports-mobile.png" });
});
