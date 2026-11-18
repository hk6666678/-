import {test,expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
test('restructured research analysis: outputs tabs, rules page, comparison handoff',async({page})=>{
 test.setTimeout(90000);
 await page.goto('/');await page.getByLabel('用户名',{exact:true}).fill('synthetic-admin');await page.getByLabel('密码',{exact:true}).fill('Synthetic-password-123!');await page.getByRole('button',{name:'登录平台'}).click();await expect(page.getByRole('heading',{name:'欢迎回到工作台'})).toBeVisible();
 const session=await(await page.request.get('/api/me',{timeout:10000})).json();const headers={'X-CSRF-Token':session.csrf_token};const original=(await(await page.request.get(`/api/users/${session.user.id}/grants`)).json()).grants;
 async function grants(values:unknown){const me=await(await page.request.get('/api/me',{timeout:10000})).json();return page.request.put(`/api/users/${session.user.id}/grants`,{headers,data:{expected_version:me.user.version,request_id:crypto.randomUUID(),grants:values}});}
 try{
  expect((await grants(['basic','papers'].flatMap(category=>['maintain','view','identity','download','labels','analyze','candidate_rules'].map(operation=>({category,operation,college:'重组合成学院',major:'重组合成专业'}))))).status()).toBe(200);
  const workbook=execFileSync('../.venv/Scripts/python.exe',['-c',"import sys,io; from openpyxl import Workbook; w=Workbook();s=w.active;s.append(['AQP-PGS','basic','1']);s.append(['学号','姓名','所属学院','专业','培养层次','入学年份']);s.append(['RESTRUCTURE-SYN-01','重组合成学生','重组合成学院','重组合成专业','硕士','2025']);o=io.BytesIO();w.save(o);sys.stdout.buffer.write(o.getvalue())"],{env:{...process.env,PYTHONUTF8:'1'}});
  const preview=await page.request.post('/api/imports/basic/preview',{headers,multipart:{source_department:'重组合成来源',file:{name:'synthetic.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:workbook}}});expect(preview.status()).toBe(200);const batch=await preview.json();expect((await page.request.post(`/api/imports/${batch.id}/confirm`,{headers})).status()).toBe(200);
  const students=await(await page.request.get('/api/students')).json();const student=students.items.find((s:{student_number:string})=>s.student_number==='RESTRUCTURE-SYN-01');expect(student).toBeTruthy();
  // 科研成果导入：一个入口带标签页切换四类成果
  await page.getByRole('button',{name:'科研成果导入',exact:true}).click();
  await expect(page.getByRole('heading',{name:'已发表科研论文',exact:true})).toBeVisible();
  await page.getByRole('tab',{name:'专利',exact:true}).click();
  await expect(page.getByRole('heading',{name:'专利',exact:true})).toBeVisible();
  await page.getByRole('tab',{name:'会议',exact:true}).click();
  await expect(page.getByRole('heading',{name:'会议',exact:true})).toBeVisible();
  // 业务规则管理页：三段规则集中
  await page.getByRole('button',{name:'业务规则管理',exact:true}).click();
  await page.getByText('课程通过与培养要求',{exact:true}).click();
  await expect(page.getByRole('heading',{name:'课程通过规则与培养要求',exact:true})).toBeVisible();
  await page.getByText('模拟评分规则',{exact:true}).click();
  await expect(page.getByRole('heading',{name:'人才评价规则（模拟）',exact:true})).toBeVisible();
  await page.getByText('论文候选规则',{exact:true}).click();
  await expect(page.getByRole('heading',{name:'优秀论文候选规则',exact:true})).toBeVisible();
  // 学位论文上传与质量两页串联，生成比较后候选页自动带入
  await page.getByRole('button',{name:'学位论文上传',exact:true}).click();
  await page.getByLabel('研究生',{exact:true}).selectOption(String(student.id));await page.getByLabel('标题',{exact:true}).fill('重组合成论文');await page.getByLabel('论文PDF').setInputFiles({name:'synthetic.pdf',mimeType:'application/pdf',buffer:Buffer.from('synthetic damaged PDF')});await page.getByLabel('已核对 PDF 涉及的全部学生').check();await page.getByRole('button',{name:'上传新版本并排队'}).click();await expect(page.getByText('文件损坏或不可用',{exact:false})).toBeVisible();
  const papers=(await(await page.request.get('/api/papers')).json()).items;const paper=papers.find((p:{student_id:number})=>p.student_id===student.id);expect(paper).toBeTruthy();
  await page.getByRole('button',{name:'学位论文质量',exact:true}).click();
  await page.getByLabel('比较论文',{exact:true}).selectOption(String(paper.id));
  await page.getByRole('button',{name:'生成同类比较'}).click();
  await expect(page.getByText('信息不足或缺少同类对照组，不自动跨学科比较。',{exact:false})).toBeVisible();
  const comparisons=(await(await page.request.get('/api/paper-comparisons')).json()).items;expect(comparisons.length).toBeGreaterThan(0);const fresh=comparisons[0];
  const comparisonSelect=page.getByLabel('当前比较快照',{exact:true});
  await expect(comparisonSelect).toHaveValue(String(fresh.id));
  await expect(page.getByRole('status')).toContainText(`已带入刚生成的比较快照 #${fresh.id}`);
  await page.getByRole('button',{name:'生成候选结果新版本'}).click();
  await expect(page.getByText('无适用启用规则，证据不足。').first()).toBeVisible();
 } finally {if(original)await grants(original);}
});
