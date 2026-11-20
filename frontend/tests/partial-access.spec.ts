import { expect, test, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";

test("the same student's results respect basic and course view-only access", async ({ page, browser, baseURL }) => {
  const college = "可见范围验收学院", major = "可见范围验收专业";
  const number = "SCOPE-001", name = "许清和", patent = "受限专利样本甲";
  const password = "Synthetic-password-123!";
  async function login(p: Page, username: string) {
    await p.goto("/");
    await p.getByLabel("用户名",{exact:true}).fill(username);
    await p.getByLabel("密码",{exact:true}).fill(password);
    await p.getByRole("button",{name:"登录平台"}).click();
    await expect(p.getByRole("heading",{name:"Agent 智能问答"})).toBeVisible();
  }
  await login(page,"synthetic-admin");
  const me = await (await page.request.get("/api/me")).json();
  const headers = {"X-CSRF-Token":me.csrf_token};
  const readerResponse = await page.request.post("/api/users",{headers,data:{
    username:"scope-reader",password,roles:["college_analyst"],request_id:crypto.randomUUID(),
  }});
  expect(readerResponse.ok()).toBeTruthy();
  const reader = await readerResponse.json();
  async function grants(user: {id:number;version:number}, categories:string[], operations:string[]) {
    const result = await page.request.put(`/api/users/${user.id}/grants`,{headers,data:{
      expected_version:user.version,request_id:crypto.randomUUID(),
      grants:categories.flatMap(category=>operations.map(operation=>({category,operation,college,major}))),
    }});
    expect(result.ok()).toBeTruthy();
  }
  await grants(me.user,["basic","courses","topic","midterm","papers","patents","research_papers","awards","conferences","mentor_groups","talent_evaluation"],["view","identity","maintain","analyze"]);
  await grants(reader,["basic","courses"],["view"]);
  async function seed(category:string, columns:string[], row:(string|number)[], preview:string, confirm:(id:string)=>string) {
    const buffer=execFileSync("../.venv/Scripts/python.exe",["-c",
      "import sys,json,io;from openpyxl import Workbook;w=Workbook();s=w.active;[s.append(row) for row in json.load(sys.stdin)];b=io.BytesIO();w.save(b);sys.stdout.buffer.write(b.getvalue())"],
      {input:JSON.stringify([["AQP-PGS",category,"1"],columns,row]),env:{...process.env,PYTHONUTF8:"1"}});
    const response=await page.request.post(preview,{headers,multipart:{source_department:"模拟培养办",file:{name:"synthetic.xlsx",mimeType:"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",buffer}}});
    expect(response.ok()).toBeTruthy();
    const batch=await response.json();
    const saved=await page.request.post(confirm(batch.id),{headers,data:{accept_changes:false}});
    expect(saved.ok()).toBeTruthy();
  }
  await seed("basic",["学号","姓名","所属学院","专业","培养层次","入学年份"],[number,name,college,major,"硕士","2025"],"/api/imports/basic/preview",id=>`/api/imports/${id}/confirm`);
  await seed("courses",["学号","姓名","课程编号","课程名称","修读学期","考核次数","评分制度","原始成绩","业务通过结果","所属学院","专业"],[number,name,"SC01","验收数学","2025秋",1,"百分制",85,"通过",college,major],"/api/imports/courses/preview",id=>`/api/imports/courses/${id}/confirm`);
  await seed("patents",["申请号","专利名称","学号","姓名","作者次序","参与角色","所属学院","专业","专利类型","申请日期"],["SC-PAT01",patent,number,name,1,"第一作者",college,major,"发明","2026-03-01"],"/api/patents/preview",id=>`/api/patents/previews/${id}/confirm`);
  const [student]=(await (await page.request.get("/api/students?q="+number)).json()).items;
  const context=await browser.newContext({baseURL});
  const restricted=await context.newPage();
  for(const p of [page,restricted]){
    const full=p===page;
    if(!full) await login(p,"scope-reader");
    const click=(label:string)=>p.getByRole("button",{name:label,exact:true}).click();
    await click("基础导入与学生档案");
    await expect(p.getByRole("row").filter({hasText:student.research_id})).toBeVisible();
    await p.getByRole("row").filter({hasText:student.research_id}).getByRole("button",{name:"查看来源"}).click();
    await expect(p.locator(".timeline")).toContainText("2025秋");
    await click("培养过程分析");
    await p.getByLabel("研究生",{exact:true}).selectOption(String(student.id));
    await click("查看培养过程");
    await expect(p.getByRole("heading",{name:"个人培养过程"})).toBeVisible();
    if(full) await expect(p.locator(".student-brief")).toContainText("1 条考核记录");
    else {
      await expect(p.locator(".student-brief")).toContainText("此范围操作未授权");
      await expect(p.getByText("已分析环节暂无已确认预警")).toHaveCount(0);
    }
    await click("科研成果导入");
    await p.getByRole("tab",{name:"专利",exact:true}).click();
    if(full) await expect(p.getByRole("cell",{name:new RegExp(patent)})).toBeVisible();
    else {
      await expect(p.getByText(patent,{exact:false})).toHaveCount(0);
      await expect(p.getByText("当前账号没有此类成果的查看权限。")).toBeVisible();
      await expect(p.locator(".summary-pair")).toHaveCount(0);
    }
    await click("学位论文质量");
    await expect(p.getByText(full ? "当前授权范围内暂无学位论文。" : "当前账号没有学位论文查看权限。")).toBeVisible();
    await expect(p.getByRole("button",{name:"生成同类比较"})).toBeDisabled();
    await click("导师与课题组数据");
    await click("查询关系事实");
    await p.waitForFunction(()=>document.querySelector('[aria-label="关系事实结果"],[role="alert"]'));
    if (full) await expect(p.locator(".mentor-fact-summary")).toContainText("有效指导关系：0");
    else {
      await expect(p.getByRole("alert")).toContainText("指导关系统计需要查看和分析权限");
      await expect(p.locator(".mentor-fact-summary")).toHaveCount(0);
    }
    const dashboard=p.waitForResponse("**/api/evaluation-snapshots/dashboard");
    await click("拔尖人才模拟评价");
    expect((await dashboard).ok()).toBeTruthy();
    await p.getByLabel("学生研究编号",{exact:true}).selectOption(String(student.id));
    await click("保存新评分快照");
    if(full) await expect(p.locator("#evaluation-evidence")).toContainText("数据不完整");
    else {
      await expect(p.locator('[role="alert"]').first()).toBeVisible();
      await expect(p.locator("#evaluation-evidence")).toHaveCount(0);
      await expect(p.getByRole("alert").first()).toContainText("人才评价授权不足");
    }
  }
  await context.close();
});
