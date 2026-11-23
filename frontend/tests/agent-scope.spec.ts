import { expect, test, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";

test("agent answers and evidence respect the student's program and stage permissions", async ({ page, browser, baseURL }) => {
  test.setTimeout(90000);
  const password = "Synthetic-password-123!";
  const college = "问答验收学院", major = "测试甲专业", other = "测试乙专业";
  const number = "990001", name = "陈清禾", title = "合成选题水文测量";
  async function login(p: Page, username: string) {
    await p.goto("/");
    await p.getByLabel("用户名", {exact:true}).fill(username);
    await p.getByLabel("密码", {exact:true}).fill(password);
    await p.getByRole("button", {name:"登录平台"}).click();
    await expect(p.getByLabel("问题", {exact:true})).toBeVisible();
  }
  await login(page, "synthetic-admin");
  const me = await (await page.request.get("/api/me")).json();
  const headers = {"X-CSRF-Token":me.csrf_token};
  const reader = await (await page.request.post("/api/users", {headers, data:{
    username:"agent-scope-reader", password, roles:["college_analyst"], request_id:crypto.randomUUID(),
  }})).json();
  for (const user of [me.user, reader]) {
    const full = user.id === me.user.id;
    const grants = (full ? [major, other] : [major]).flatMap(major =>
      (full ? ["basic","courses","topic","midterm"] : ["basic","courses"]).flatMap(category =>
        (full ? ["maintain","identity","view","analyze"] : category === "basic" ? ["identity","view"] : ["view","analyze"])
          .map(operation => ({college,major,category,operation}))));
    expect((await page.request.put(`/api/users/${user.id}/grants`, {headers,data:{
      grants, expected_version:user.version, request_id:crypto.randomUUID(),
    }})).ok()).toBeTruthy();
  }
  async function seed(category:string, rows:(string|number)[][], preview:string, confirmation:string) {
    const buffer = execFileSync("../.venv/Scripts/python.exe", ["-c",
      "import io,json,sys;from openpyxl import Workbook;w=Workbook();[w.active.append(r) for r in json.load(sys.stdin)];b=io.BytesIO();w.save(b);sys.stdout.buffer.write(b.getvalue())"],
      {input:JSON.stringify([["AQP-PGS",category,"1"], ...rows]), env:{...process.env,PYTHONUTF8:"1"}});
    const response = await page.request.post(preview,{headers,multipart:{source_department:"问答验收",file:{name:"test.xlsx",mimeType:"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",buffer}}});
    expect(response.ok(),await response.text()).toBeTruthy();
    const {id} = await response.json();
    const saved = await page.request.post(`${confirmation}/${id}/confirm`,{headers,data:{accept_changes:false}});
    expect(saved.ok(),await saved.text()).toBeTruthy();
  }
  await seed("basic",[["学号","姓名","所属学院","专业","培养层次","入学年份"],[number,name,college,major,"硕士","2022"],["990002","林清秋",college,other,"硕士","2022"]],"/api/imports/basic/preview","/api/imports");
  await seed("courses",[["学号","姓名","课程编号","课程名称","修读学期","考核次数","评分制度","原始成绩","所属学院","专业"],
    ...["2022春","2022秋","2023春","2023秋","2024春","2024秋"].map((term,i)=>[number,name,"C"+i,"统计"+i,term,1,"百分制",[80,82,81,82,80,60][i],college,major])],"/api/imports/courses/preview","/api/imports/courses");
  await seed("topic",[["学号","姓名","所属学院","专业","考核批次","评分制度","原始成绩","选题标题","计划日期","实际日期"],[number,name,college,major,"甲批","百分制",81,title,"2025-03-10","2025-03-18"]],"/api/milestones/topic/preview","/api/milestone-imports");
  await seed("midterm",[["学号","姓名","所属学院","专业","考核批次","评分制度","原始成绩","计划日期","实际日期","业务通过结果"],[number,name,college,major,"中期密封批次","百分制",85,"2025-09-17","2025-09-16","通过"]],"/api/milestones/midterm/preview","/api/milestone-imports");
  const click = (p:Page, label:string)=>p.getByRole("button",{name:label,exact:true}).click();
  await click(page,"培养过程分析");
  const select = page.getByLabel("研究生",{exact:true});
  const option = select.locator("option").filter({hasText:number});
  await expect(option).toHaveCount(1);
  await select.selectOption(await option.getAttribute("value") as string);
  await click(page,"查看培养过程");
  await page.getByText(/研究记录.*2 条信号/).click();
  for (const label of ["课程均分低于下限","选题超期"]) {
    const signal = page.locator("li").filter({hasText:label}).first();
    await signal.locator("summary").click();
    const source = await signal.getByRole("link").first().getAttribute("href");
    const response = await page.request.get(source!);
    expect(response.ok()).toBeTruthy();
    expect(await response.text()).toContain(label === "选题超期" ? title : "百分制");
  }

  // Only the model planner and prose are synthetic. The application computes the scoped count.
  const model = createServer(async (req,res)=>{
    let body = "";
    for await (const chunk of req) body += chunk;
    const prompt = JSON.parse(JSON.parse(body).messages.at(-1).content);
    const content = prompt.tool_result ? `当前授权范围共 ${prompt.tool_result.total} 名学生。` : JSON.stringify({tool:"student_counts"});
    res.writeHead(200,{"content-type":"application/json"});
    res.end(JSON.stringify({id:"synthetic",object:"chat.completion",model:"browser-test",choices:[{index:0,finish_reason:"stop",message:{role:"assistant",content}}]}));
  });
  await new Promise<void>(resolve=>model.listen(0,"127.0.0.1",resolve));
  const original = await (await page.request.get("/api/model/config")).json();
  const context = await browser.newContext({baseURL});
  try {
    const config = await page.request.put("/api/model/config",{headers,data:{...original,expected_version:original.version,enabled:true,approved:true,approval_reference:"隔离验收",
      key_env:"AQP_MODEL_KEY_BROWSER_TEST",allowed_purposes:["agent"],model:"browser-test",endpoint:`http://127.0.0.1:${(model.address() as AddressInfo).port}/v1`}});
    expect(config.ok(),await config.text()).toBeTruthy();
    for (const full of [true,false]) {
      const p = full ? page : await context.newPage();
      if (!full) await login(p,"agent-scope-reader");
      await click(p,"基础导入与学生档案");
      await expect(p.locator(".student-roster tbody tr")).toHaveCount(full ? 2 : 1);
      await expect(p.locator(".student-roster")).toContainText(name);
      await click(p,"Agent 智能问答");
      async function ask(question:string) {
        await p.getByLabel("问题",{exact:true}).fill(question);
        const result = p.waitForResponse(r=>r.url().endsWith("/api/agent/query"));
        await click(p,"发送问题");
        const response = await result;
        expect(response.ok(),await response.text()).toBeTruthy();
        return response.json();
      }
      const count = await ask("我有权限查看多少名学生？");
      expect(count.tool_result.total).toBe(full ? 2 : 1);
      await expect(p.locator(".agent-answer").last()).toContainText(full ? "2 名" : "1 名");
      const alert = await ask(`学号 ${number} 的学生触发了哪些预警？`);
      const answer = p.locator(".agent-answer").last();
      await expect(answer).toContainText("课程趋势：低于控制下限");
      await expect(answer).toContainText(full ? "选题超期" : "选题未授权");
      await answer.locator("summary").first().click();
      if (!full) {
        await expect(answer).toContainText("中期未授权");
        expect(alert.tool_result.milestone_trends).toBeUndefined();
        expect(alert.evidence_links.map((link:{label:string})=>link.label)).toEqual(["学生档案"]);
      }
      const texts = [JSON.stringify(alert),await answer.innerText()];
      for (const link of await answer.getByRole("link").all()) {
        const response = await p.request.get((await link.getAttribute("href"))!);
        expect(response.ok()).toBeTruthy();
        texts.push(await response.text());
      }
      if (!full) expect(texts.join(" ")).not.toMatch(/合成选题水文测量|中期密封批次|2025-03-(10|18)|2025-09-1[67]|选题超期|(?:选题|中期)有\s*1\s*条/);
    }
  } finally {
    const current = await (await page.request.get("/api/model/config")).json();
    await page.request.put("/api/model/config",{headers,data:{...original,expected_version:current.version}});
    await context.close();
    model.close();
  }
});
