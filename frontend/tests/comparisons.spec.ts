import {test,expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
test('synthetic expert label and comparison history',async({page})=>{
 test.setTimeout(90000);
 await page.goto('/');await page.getByLabel('用户名',{exact:true}).fill('synthetic-admin');await page.getByLabel('密码',{exact:true}).fill('Synthetic-password-123!');await page.getByRole('button',{name:'登录平台'}).click();await expect(page.getByRole('heading',{name:'Agent 智能问答'})).toBeVisible();
 const session=await(await page.request.get('/api/me',{timeout:10000})).json();const headers={'X-CSRF-Token':session.csrf_token};const original=(await(await page.request.get(`/api/users/${session.user.id}/grants`)).json()).grants;
 async function grants(values:unknown){const me=await(await page.request.get('/api/me',{timeout:10000})).json();return page.request.put(`/api/users/${session.user.id}/grants`,{headers,data:{expected_version:me.user.version,request_id:crypto.randomUUID(),grants:values}});}
 try{
  expect((await grants(['basic','papers'].flatMap(category=>['maintain','view','identity','download','labels','analyze'].map(operation=>({category,operation,college:'比较合成学院',major:'比较合成专业'}))))).status()).toBe(200);
  const workbook=execFileSync('../.venv/Scripts/python.exe',['-c',"import sys,io; from openpyxl import Workbook; w=Workbook();s=w.active;s.append(['AQP-PGS','basic','1']);s.append(['学号','姓名','所属学院','专业','培养层次','入学年份']);s.append(['COMPARE-SYN-14','论文合成学生','比较合成学院','比较合成专业','硕士','2025']);o=io.BytesIO();w.save(o);sys.stdout.buffer.write(o.getvalue())"],{env:{...process.env,PYTHONUTF8:'1'}});
 const preview=await page.request.post('/api/imports/basic/preview',{headers,multipart:{source_department:'论文合成来源',file:{name:'synthetic.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:workbook}}});expect(preview.status()).toBe(200);const batch=await preview.json();expect((await page.request.post(`/api/imports/${batch.id}/confirm`,{headers})).status()).toBe(200);
 const students=await(await page.request.get('/api/students')).json();const student=students.items.find((s:{student_number:string})=>s.student_number==='COMPARE-SYN-14');expect(student).toBeTruthy();
 await page.getByRole('button',{name:'学位论文上传',exact:true}).click();await page.getByLabel('研究生',{exact:true}).selectOption(String(student.id));await page.getByLabel('标题',{exact:true}).fill('合成论文闭环');await page.getByLabel('论文PDF').setInputFiles({name:'synthetic.pdf',mimeType:'application/pdf',buffer:Buffer.from('synthetic damaged PDF')});await page.getByLabel('已核对 PDF 涉及的全部学生').check();await page.getByRole('button',{name:'上传新版本并排队'}).click();await expect(page.getByText('文件损坏或不可用',{exact:false})).toBeVisible();
 const papers=(await(await page.request.get('/api/papers')).json()).items;const paper=papers.find((p:{student_id:number})=>p.student_id===student.id);
 await page.getByRole('button',{name:'学位论文质量',exact:true}).click();await page.getByLabel('比较论文',{exact:true}).selectOption(String(paper.id));await expect(page.getByText('待评',{exact:false}).first()).toBeVisible();
 await page.getByText('样本标签 · 待评',{exact:true}).click();await page.getByLabel('样本标签',{exact:true}).selectOption('优秀');await page.getByLabel('业务确认人').fill('合成专家14');await page.getByLabel('确认依据').fill('合成确认书14');await page.getByRole('button',{name:'保存标签新版本'}).click();await expect(page.getByText('合成确认书14',{exact:false})).toBeVisible();
 await page.getByRole('button',{name:'生成同类比较'}).click();await expect(page.getByText('信息不足或缺少同类对照组，不自动跨学科比较。',{exact:false})).toBeVisible();
 await page.getByText('比较版本与导出',{exact:true}).click();await page.getByRole('button',{name:'检查历史比较是否过时'}).click();


 } finally {if(original)await grants(original);}
});

test("a late history response cannot replace another paper's comparison", async ({ page }) => {
  const paperA = { id: 1, title: "合成论文甲", version: 1, discipline: "计算机" };
  const paperB = { ...paperA, id: 2, title: "合成论文乙" };
  const comparison = (id: number, pages: number) => ({
    id, stale: false, target_features: { page_count: pages },
    groups: { 普通: { sample_count: 1, features: { page_count: { mean: 12, denominator: 1 } } } },
  });
  await page.route("**/api/papers", route => route.fulfill({ json: { items: [paperA, paperB] } }));
  await page.route("**/api/papers/*/labels", route => route.fulfill({ json: { label: "待评", version: 0, items: [] } }));
  await page.route("**/api/papers/1/comparisons", route => route.fulfill({ json: comparison(11, 31) }));
  await page.route("**/api/papers/2/comparisons", route => route.fulfill({ json: comparison(22, 42) }));
  let release!: () => void;
  const delayed = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/paper-comparisons/11", async route => {
    await delayed;
    await route.fulfill({ json: comparison(11, 31) });
  });
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page.getByLabel("密码", { exact: true }).fill("Synthetic-password-123!");
  await page.getByRole("button", { name: "登录平台" }).click();
  await page.getByRole("button", { name: "学位论文质量", exact: true }).click();
  const picker = page.getByLabel("比较论文", { exact: true });
  const generate = page.getByRole("button", { name: "生成同类比较" });
  await picker.selectOption("1");
  await generate.click();
  await page.getByText("比较版本与导出", { exact: true }).click();
  const historyRequest = page.waitForRequest("**/api/paper-comparisons/11");
  await page.getByRole("button", { name: "检查历史比较是否过时" }).click();
  await historyRequest;
  await picker.selectOption("2");
  await generate.click();
  await expect(page.getByRole("cell", { name: "42", exact: true })).toBeVisible();
  const lateResponse = page.waitForResponse("**/api/paper-comparisons/11");
  release();
  await (await lateResponse).finished();
  await expect(page.getByText("合成论文乙", { exact: true })).toBeVisible();
  const exportLink = page.getByRole("link", { name: "下载比较 Excel", includeHidden: true });
  await expect(exportLink).toHaveAttribute("href", "/api/paper-comparisons/22/export", { timeout: 2000 });
  await expect(page.getByRole("cell", { name: "42", exact: true })).toBeVisible();
});

