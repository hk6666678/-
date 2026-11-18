import { execFileSync } from "node:child_process";
import { test, expect } from "@playwright/test";
test("simulation rule, scoring, history, charts and authorized export", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page
    .getByLabel("密码", { exact: true })
    .fill("Synthetic-password-123!");
  await page.getByRole("button", { name: "登录平台" }).click();
  await expect(
    page.getByRole("heading", { name: "欢迎回到工作台" }),
  ).toBeVisible();
  const session = await (await page.request.get("/api/me")).json();
  expect(
    (
      await page.request.put(`/api/users/${session.user.id}/grants`, {
        headers: { "X-CSRF-Token": session.csrf_token },
        data: {
          expected_version: session.user.version,
          request_id: crypto.randomUUID(),
          grants: [
            { category: "basic", operation: "maintain" },
            { category: "basic", operation: "view" },
            { category: "basic", operation: "identity" },
            { category: "basic", operation: "analyze" },
            { category: "basic", operation: "export" },
            { category: "patents", operation: "maintain" },
            { category: "patents", operation: "view" },
            { category: "patents", operation: "identity" },
            { category: "patents", operation: "analyze" },
            { category: "patents", operation: "export" },
            { category: "research_papers", operation: "maintain" },
            { category: "research_papers", operation: "view" },
            { category: "research_papers", operation: "identity" },
            { category: "research_papers", operation: "analyze" },
            { category: "research_papers", operation: "export" },
            { category: "awards", operation: "maintain" },
            { category: "awards", operation: "view" },
            { category: "awards", operation: "identity" },
            { category: "awards", operation: "analyze" },
            { category: "awards", operation: "export" },
          ].map((grant) => ({
            ...grant,
            college: "合成学院",
            major: "合成专业",
          })).concat(
            [
              "maintain",
              "view",
              "identity",
              "analyze",
              "activate_evaluation",
              "export",
            ].map((operation) => ({
              category: "talent_evaluation",
              operation,
              college: "合成学院",
              major: "合成专业",
            })),
          ),
        },
      })
    ).status(),
  ).toBe(200);
  await page.getByRole("button", { name: "基础导入与学生档案" }).click();
  const template = await page.request.get("/api/templates/basic?sample=true");
  expect(template.status()).toBe(200);
  await page.getByText("导入学生档案", { exact: true }).click();
  await page.getByLabel("来源部门", { exact: true }).fill("评分专项合成数据源");
  await page.getByLabel("基础信息 Excel", { exact: true }).setInputFiles({
    name: "synthetic-basic.xlsx",
    mimeType:
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: execFileSync(
      "../.venv/Scripts/python.exe",
      [
        "-c",
        "import sys,io;from openpyxl import load_workbook;w=load_workbook(io.BytesIO(sys.stdin.buffer.read()));w.active.cell(3,1,'SYN-EVAL-0001');w.active.cell(3,2,'评分专项合成学生');o=io.BytesIO();w.save(o);sys.stdout.buffer.write(o.getvalue())",
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
  await page.locator("summary").filter({ hasText: /^导入/ }).first().click();
  await page.getByLabel("来源部门", { exact: true }).fill("评分专项合成专利科");
  const uploadOutput = async (
    category: string,
    filename: string,
    header: string[],
    row: (string | number)[],
  ) => {
    await page.getByLabel("标准 Excel 文件", { exact: true }).setInputFiles({
      name: filename,
      mimeType:
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      buffer: execFileSync(
        "../.venv/Scripts/python.exe",
        [
          "-c",
          `import sys,io;from openpyxl import Workbook;w=Workbook();a=w.active;a.append(['AQP-PGS','${category}','1']);a.append(${JSON.stringify(header)});a.append(${JSON.stringify(row)});o=io.BytesIO();w.save(o);sys.stdout.buffer.write(o.getvalue())`,
        ],
        { env: { ...process.env, PYTHONUTF8: "1" } },
      ),
    });
    await page.getByRole("button", { name: "预览导入", exact: true }).click();
    await expect(page.getByRole("heading", { name: "导入预览" })).toBeVisible();
    await page.getByRole("button", { name: "确认导入", exact: true }).click();
    await expect(
      page.getByRole("cell", { name: "评分专项合成学生", exact: false }),
    ).toBeVisible();
  };
  const participant = [
    "SYN-EVAL-0001",
    "评分专项合成学生",
    1,
    "第一作者",
    "合成学院",
    "合成专业",
  ];
  await uploadOutput(
    "patents",
    "synthetic-patents.xlsx",
    [
      "申请号",
      "专利名称",
      "学号",
      "姓名",
      "作者次序",
      "参与角色",
      "所属学院",
      "专业",
      "专利类型",
      "申请日期",
    ],
    ["PAT-EVAL-0001", "合成评分专利", ...participant, "发明", "2026-01-01"],
  );
  await page.getByRole("tab", { name: "科研论文", exact: true }).click();
  await page.locator("summary").filter({ hasText: /^导入/ }).first().click();
  await page.getByLabel("来源部门", { exact: true }).fill("评分专项合成论文科");
  await uploadOutput(
    "research_papers",
    "synthetic-papers.xlsx",
    [
      "业务编号/DOI",
      "论文标题",
      "学号",
      "姓名",
      "作者次序",
      "参与角色",
      "所属学院",
      "专业",
      "发表年份",
    ],
    ["PAPER-EVAL-0001", "合成评分论文", ...participant, 2025],
  );
  await page.getByRole("tab", { name: "获奖项目", exact: true }).click();
  await page.locator("summary").filter({ hasText: /^导入/ }).first().click();
  await page.getByLabel("来源部门", { exact: true }).fill("评分专项合成获奖科");
  await uploadOutput(
    "awards",
    "synthetic-awards.xlsx",
    [
      "业务编号",
      "获奖项目名称",
      "学号",
      "姓名",
      "作者次序",
      "参与角色",
      "所属学院",
      "专业",
      "获奖等级",
      "获奖年份",
    ],
    ["AWARD-EVAL-0001", "合成评分获奖", ...participant, "一等奖", "2026"],
  );
  await page
    .getByRole("button", { name: "业务规则管理", exact: true })
    .click();
  await page.getByText("模拟评分规则", { exact: true }).click();
  const evaluationRules = page.locator("article.card", {
    has: page.getByRole("heading", {
      name: "人才评价规则（模拟）",
      exact: true,
    }),
  });
  await evaluationRules
    .getByText("新建不可覆盖的规则草稿", { exact: true })
    .click();
  await evaluationRules.getByLabel("规则名称", { exact: true }).fill("合成演示规则");
  await evaluationRules
    .getByLabel("学院", { exact: true })
    .selectOption("__other_college__");
  await evaluationRules
    .getByLabel("其他学院名称", { exact: true })
    .fill("合成学院");
  await evaluationRules.getByLabel("专业", { exact: true }).fill("合成专业");
  await evaluationRules.getByRole("button", { name: "添加指标" }).click();
  await evaluationRules.getByRole("button", { name: "添加指标" }).click();
  await evaluationRules
    .getByLabel("指标 2", { exact: true })
    .selectOption("research_paper_count");
  await evaluationRules
    .getByLabel("指标 3", { exact: true })
    .selectOption("award_count");
  await evaluationRules
    .getByRole("button", { name: "保存模拟草稿" })
    .click();
  await expect(page.getByRole("status")).toContainText("尚未启用");
  await evaluationRules
    .getByLabel("业务确认人", { exact: true })
    .fill("合成业务确认人");
  await evaluationRules
    .getByLabel("确认依据", { exact: true })
    .fill("仅验证模拟流程，不作为真实人才标准");
  await evaluationRules
    .getByLabel("确认仅用于模拟演示", { exact: true })
    .check();
  await evaluationRules
    .getByRole("button", { name: "确认启用模拟规则" })
    .click();
  await expect(page.getByRole("status")).toContainText("已启用模拟版本");
  await expect(
    evaluationRules.getByRole("cell", { name: "模拟已启用", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "拔尖人才模拟评价", exact: true })
    .click();
  await expect(
    page.getByLabel("学生研究编号", { exact: true }),
  ).toHaveJSProperty("tagName", "SELECT");
  await expect(
    page.getByLabel("学生内部编号", { exact: true }),
  ).toHaveCount(0);
  await page.getByText("按专业缩小学生列表", { exact: true }).click();
  await page
    .getByLabel("学生列表专业筛选", { exact: true })
    .selectOption("合成专业");
  const studentSelect = page.getByLabel("学生研究编号", { exact: true });
  // Shared suite server: other specs add students to the same major, so locate
  // this spec's own student by its unique student number instead of position.
  const roster = await (
    await page.request.get(
      `/api/students?limit=200&offset=0&major=${encodeURIComponent("合成专业")}`,
    )
  ).json();
  const mine = roster.items.find(
    (item: { student_number?: string }) => item.student_number === "SYN-EVAL-0001",
  );
  if (!mine) throw new Error("evaluation student missing from roster");
  await studentSelect.selectOption(String(mine.id));
  await page.getByRole("button", { name: "保存新评分快照" }).click();
  await expect(
    page.getByRole("heading", { name: /快照 #1 · 10\.00 \/ 100/ }),
  ).toBeVisible();
  await expect(page.locator("svg[aria-label='指标雷达图']")).toBeVisible();
  await expect(
    page.getByText("有效快照不足两个，暂不绘制连线。"),
  ).toBeVisible();
  // A second real patent raises the score, so the growth line has an honest
  // slope between two genuine snapshots.
  await page.getByRole("button", { name: "科研成果导入", exact: true }).click();
  await page.getByRole("tab", { name: "专利", exact: true }).click();
  await page.locator("summary").filter({ hasText: /^导入/ }).first().click();
  await page.getByLabel("来源部门", { exact: true }).fill("评分专项合成专利科");
  await uploadOutput(
    "patents",
    "synthetic-patents-2.xlsx",
    [
      "申请号",
      "专利名称",
      "学号",
      "姓名",
      "作者次序",
      "参与角色",
      "所属学院",
      "专业",
      "专利类型",
      "申请日期",
    ],
    ["PAT-EVAL-0002", "合成评分专利二", ...participant, "发明", "2026-02-01"],
  );
  await page
    .getByRole("button", { name: "拔尖人才模拟评价", exact: true })
    .click();
  await page.getByText("查看或更换评分规则", { exact: true }).click();
  await page.getByLabel("选择规则 1", { exact: true }).check();
  await page.getByText("按专业缩小学生列表", { exact: true }).click();
  await page
    .getByLabel("学生列表专业筛选", { exact: true })
    .selectOption("合成专业");
  const roster2 = await (
    await page.request.get(
      `/api/students?limit=200&offset=0&major=${encodeURIComponent("合成专业")}`,
    )
  ).json();
  const mine2 = roster2.items.find(
    (item: { student_number?: string }) => item.student_number === "SYN-EVAL-0001",
  );
  if (!mine2) throw new Error("evaluation student missing from roster");
  await page
    .getByLabel("学生研究编号", { exact: true })
    .selectOption(String(mine2.id));
  await page.getByRole("button", { name: "保存新评分快照" }).click();
  await expect(
    page.getByRole("heading", { name: /快照 #2 · 13\.33 \/ 100/ }),
  ).toBeVisible();
  await expect(page.getByText("共2个有效快照点。")).toBeVisible();
  const evidenceButton = page.getByRole("button", { name: "查看快照 #2 的证据" });
  await expect(evidenceButton).toBeVisible();
  await expect(page.getByRole("button", { name: "查看快照 #1 的证据" })).toHaveCount(0);
  await evidenceButton.click();
  await expect(page.getByRole("heading", { name: /快照 #2 · 13\.33 \/ 100/ })).toBeVisible();
  // Snapshots saved within the same second overlap on the honest time axis,
  // so assert the plotted points rather than a zero-width connecting line.
  await expect(
    page.locator("svg[aria-label='总分成长曲线'] circle"),
  ).toHaveCount(2);
  await page.getByText("查看历史评分", { exact: true }).click();
  const historySelect = page.getByLabel("历史快照", { exact: true });
  await expect(historySelect.locator("option")).toHaveCount(3);
  await historySelect.selectOption("1");
  await expect(
    page.getByRole("heading", { name: /快照 #1 · 10\.00 \/ 100/ }),
  ).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "导出评分报告（需独立导出授权）" })
    .click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("evaluation-snapshot-1.xlsx");
  await page.locator(".content").evaluate((el) => el.scrollTo(0, 0));
  await page.screenshot({
    path: "../artifacts/full07-simulation.png",
    fullPage: true,
  });
  await page
    .locator("article.card", {
      has: page.getByRole("heading", { name: /快照 #1/ }),
    })
    .screenshot({ path: "../artifacts/full07-snapshot-card.png" });
  await page.setViewportSize({ width: 550, height: 1200 });
  const columns = await page
    .locator(".evaluation-charts")
    .evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(" ").length);
  expect(columns).toBe(1);
  await page.setViewportSize({ width: 1280, height: 1000 });
  await page.locator(".content").evaluate(el => el.scrollTo(0, 0));
  await page.screenshot({ path: "../artifacts/ui-polish/evaluation-desktop.png" });
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(375);
  const wideTable = page.locator(".table-wrap").first();
  expect(await wideTable.evaluate(el => el.scrollWidth > el.clientWidth)).toBe(true);
  await wideTable.evaluate(el => { el.scrollLeft = el.scrollWidth; });
  expect(await wideTable.evaluate(el => el.scrollLeft)).toBeGreaterThan(0);
  await wideTable.evaluate(el => { el.scrollLeft = 0; });
  await page.screenshot({ path: "../artifacts/ui-polish/evaluation-mobile.png" });
});
