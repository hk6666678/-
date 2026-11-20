import {test,expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
test('synthetic semantic disabled history',async({page})=>{
 await page.goto('/');await page.getByLabel('用户名',{exact:true}).fill('synthetic-admin');await page.getByLabel('密码',{exact:true}).fill('Synthetic-password-123!');await page.getByRole('button',{name:'登录平台'}).click();await expect(page.getByRole('heading',{name:'Agent 智能问答'})).toBeVisible();
 const session=await(await page.request.get('/api/me')).json();const headers={'X-CSRF-Token':session.csrf_token};const original=(await(await page.request.get(`/api/users/${session.user.id}/grants`)).json()).grants;
 async function grants(values:unknown){const me=await(await page.request.get('/api/me')).json();return page.request.put(`/api/users/${session.user.id}/grants`,{headers,data:{expected_version:me.user.version,request_id:crypto.randomUUID(),grants:values}});}
 try{
  expect((await grants(['basic','papers'].flatMap(category=>['maintain','view','identity','download'].map(operation=>({category,operation,college:'论文合成学院',major:'论文合成专业'}))))).status()).toBe(200);
  const workbook=execFileSync('../.venv/Scripts/python.exe',['-c',"import sys,io; from openpyxl import Workbook; w=Workbook();s=w.active;s.append(['AQP-PGS','basic','1']);s.append(['学号','姓名','所属学院','专业','培养层次','入学年份']);s.append(['PAPER-SYN-12','语义合成学生','论文合成学院','论文合成专业','硕士','2025']);o=io.BytesIO();w.save(o);sys.stdout.buffer.write(o.getvalue())"],{env:{...process.env,PYTHONUTF8:'1'}});
  const preview=await page.request.post('/api/imports/basic/preview',{headers,multipart:{source_department:'论文合成来源',file:{name:'synthetic.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:workbook}}});expect(preview.status()).toBe(200);const batch=await preview.json();expect((await page.request.post(`/api/imports/${batch.id}/confirm`,{headers})).status()).toBe(200);
  const students=await(await page.request.get('/api/students')).json();const student=students.items.find((s:{student_number:string})=>s.student_number==='PAPER-SYN-12');expect(student).toBeTruthy();
  await page.getByRole('button',{name:'学位论文上传',exact:true}).click();await page.getByLabel('研究生',{exact:true}).selectOption(String(student.id));await page.getByLabel('标题',{exact:true}).fill('合成论文闭环');await page.getByLabel('论文PDF').setInputFiles({name:'synthetic.pdf',mimeType:'application/pdf',buffer:Buffer.from('synthetic damaged PDF')});await page.getByLabel('已核对 PDF 涉及的全部学生').check();await page.getByRole('button',{name:'上传新版本并排队'}).click();
  // 授权列表可能同时包含其他用例学生的论文，所有交互限定在本用例论文的条目内
  const first=(await(await page.request.get('/api/papers')).json()).items.find((p:{student_id:number})=>p.student_id===student.id);expect(first).toBeTruthy();
  const firstArticle=page.locator('article').filter({has:page.locator(`a[href="/api/papers/${first.id}/download"]`)});
  await expect(firstArticle.getByText('文件损坏或不可用',{exact:false})).toBeVisible();await firstArticle.getByRole('button',{name:'重试解析',exact:true}).click();await expect(firstArticle.getByText('文件损坏或不可用',{exact:false})).toBeVisible();const [download]=await Promise.all([page.waitForEvent('download'),firstArticle.getByRole('link',{name:'下载原件'}).click()]);expect(download.suggestedFilename()).toBe('synthetic.pdf');

 const pdf=execFileSync('../.venv/Scripts/python.exe',['-c',"import sys;sys.path.insert(0,'../backend/tests');from test_papers import text_pdf;sys.stdout.buffer.write(text_pdf())"],{env:{...process.env,PYTHONUTF8:'1',PYTHONPATH:'../backend'}});
 const uploaded=await page.request.post('/api/papers',{headers,multipart:{student_id:String(student.id),title:'合成语义论文',expected_version:'1',covered_student_ids:JSON.stringify([student.id]),file:{name:'synthetic-text.pdf',mimeType:'application/pdf',buffer:pdf}}});expect(uploaded.status()).toBe(200);
 const secondArticle=page.locator('article').filter({has:page.locator(`a[href="/api/papers/${(await uploaded.json()).id}/download"]`)});
 await page.getByRole('button',{name:'刷新进度'}).click();
 await expect(secondArticle.getByText('页数',{exact:true})).toBeVisible();
 await expect(secondArticle.getByText('字符数',{exact:true})).toBeVisible();
 await expect(secondArticle.locator('pre')).toHaveCount(0);
 await secondArticle.getByRole('button',{name:'提取智能特征'}).click();
 await expect(page.getByText('智能解析未启用；本地结果保留',{exact:false})).toBeVisible();
 await secondArticle.getByRole('button',{name:'智能特征与历史依据'}).click();
 await expect(page.getByText('paper-semantic-v1-exact-page-quote',{exact:false})).toBeVisible();
 } finally {if(original)await grants(original);}
});
