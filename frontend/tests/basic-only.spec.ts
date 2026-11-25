import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";

test("only a basic archive exists across six modules", async ({ page }) => {
  const number = "EMPTY-SIX-01";
  const name = "林知夏";
  const college = "空档验收学院";
  const major = "空档验收专业";
  const nav = (label: string) => page.getByRole("button", { name: label, exact: true }).click();
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page.getByLabel("密码", { exact: true }).fill("Synthetic-password-123!");
  await nav("登录平台");
  await expect(page.getByRole("heading", { name: "Agent 智能问答" })).toBeVisible();
  const session = await (await page.request.get("/api/me")).json();
  const categories = ["basic","courses","topic","midterm","research_papers","patents","awards","conferences","papers","mentor_groups","talent_evaluation"];
  const grants = categories.flatMap(category =>
    ["view","identity","analyze","maintain", ...(category === "talent_evaluation" ? ["activate_evaluation"] : [])]
      .map(operation => ({ category, operation, college, major })));
  const grant = await page.request.put(`/api/users/${session.user.id}/grants`, {
    headers: { "X-CSRF-Token": session.csrf_token },
    data: { expected_version: session.user.version, request_id: crypto.randomUUID(), grants },
  });
  expect(await grant.text()).not.toContain("detail");
  expect(grant.ok()).toBeTruthy();

  await nav("基础导入与学生档案");
  await page.getByText("导入学生档案", { exact: true }).click();
  await page.getByLabel("来源部门", { exact: true }).fill("验收培养办");
  const workbook = execFileSync("../.venv/Scripts/python.exe", ["-c",
    "import sys,io; from openpyxl import Workbook; w=Workbook();s=w.active;s.append(['AQP-PGS','basic','1']);s.append(['学号','姓名','所属学院','专业','培养层次','入学年份']);s.append(sys.argv[1:]+['硕士','2025']);b=io.BytesIO();w.save(b);sys.stdout.buffer.write(b.getvalue())",
    number,name,college,major], { env: { ...process.env, PYTHONUTF8: "1" } });
  await page.getByLabel("基础信息 Excel").setInputFiles({ name:"basic.xlsx",mimeType:"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",buffer:workbook });
  await nav("上传并预览");
  await nav("确认导入有效行");
  await expect(page.getByText(/已导入 1 条/)).toBeVisible();
  await page.getByLabel("查找学生档案").fill(number);
  await nav("查找学生");
  await page.getByRole("row").filter({ hasText:name }).getByRole("button",{name:"查看来源"}).click();
  await expect(page.getByRole("heading",{name:"培养时间线 · "+name})).toBeVisible();

  await nav("培养过程分析");
  await page.getByLabel("研究生",{exact:true}).selectOption({index:1});
  await nav("查看培养过程");
  await expect(page.getByText(/这名学生暂无课程、选题和中期记录/)).toBeVisible();
  await expect(page.getByText(/暂无法判断这三个环节是否触发预警/)).toBeVisible();
  await expect(page.getByText("已分析环节暂无已确认预警")).toHaveCount(0);
  await nav("个人趋势");
  await expect(page.getByText("课程暂无可用于比较的百分制学期均分，暂无法判断变化。")).toBeVisible();
  await expect(page.getByText(/中期暂无可用于比较的百分制成绩/)).toBeVisible();

  await nav("科研成果导入");
  for (const label of ["科研论文","专利","获奖项目","会议"]) {
    await page.getByRole("tab",{name:label,exact:true}).click();
    await expect(page.getByText(/当前授权范围内暂无/)).toBeVisible();
    await expect(page.locator(".summary-pair dd").first()).toHaveText("0 项");
  }
  await nav("学位论文质量");
  await expect(page.getByText("当前授权范围内暂无学位论文。")).toBeVisible();
  await expect(page.getByRole("button",{name:"生成同类比较"})).toBeDisabled();

  await nav("导师与课题组数据");
  await nav("查询关系事实");
  await expect(page.getByRole("heading",{name:"全部授权关系的指导情况"})).toBeVisible();
  await expect(page.locator(".mentor-fact-summary")).toContainText(/去重学生数：0.*有效指导关系：0/s);

  await nav("拔尖人才模拟评价");
  await page.getByLabel("学生研究编号",{exact:true}).selectOption({index:1});
  await nav("保存新评分快照");
  const score=page.locator("#evaluation-evidence");
  await expect(score.getByRole("heading",{name:/数据不完整，未形成总分/})).toBeVisible();
  await expect(score.locator(".score-lead")).toContainText(name);
  await expect(score.getByRole("region",{name:"评分缺项"})).toContainText("课程通过比例");
});
