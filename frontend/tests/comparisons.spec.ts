import {test,expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
test('synthetic expert label and comparison history',async({page})=>{
 test.setTimeout(90000);
 await page.goto('/');await page.getByLabel('用户名',{exact:true}).fill('synthetic-admin');await page.getByLabel('密码',{exact:true}).fill('Synthetic-password-123!');await page.getByRole('button',{name:'登录平台'}).click();await expect(page.getByRole('heading',{name:'欢迎回到工作台'})).toBeVisible();
 const session=await(await page.request.get('/api/me',{timeout:10000})).json();const headers={'X-CSRF-Token':session.csrf_token};const original=(await(await page.request.get(`/api/users/${session.user.id}/grants`)).json()).grants;
 async function grants(values:unknown){const me=await(await page.request.get('/api/me',{timeout:10000})).json();return page.request.put(`/api/users/${session.user.id}/grants`,{headers,data:{expected_version:me.user.version,request_id:crypto.randomUUID(),grants:values}});}
 try{
  expect((await grants(['basic','papers'].flatMap(category=>['maintain','view','identity','download','labels','analyze'].map(operation=>({category,operation,college:'比较合成学院',major:'比较合成专业'}))))).status()).toBe(200);
  const workbook=execFileSync('../.venv/Scripts/python.exe',['-c',"import sys,io; from openpyxl import Workbook; w=Workbook();s=w.active;s.append(['AQP-PGS','basic','1']);s.append(['学号','姓名','所属学院','专业','培养层次','入学年份']);s.append(['COMPARE-SYN-14','论文合成学生','比较合成学院','比较合成专业','硕士','2025']);o=io.BytesIO();w.save(o);sys.stdout.buffer.write(o.getvalue())"],{env:{...process.env,PYTHONUTF8:'1'}});
 const preview=await page.request.post('/api/imports/basic/preview',{headers,multipart:{source_department:'论文合成来源',file:{name:'synthetic.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:workbook}}});expect(preview.status()).toBe(200);const batch=await preview.json();expect((await page.request.post(`/api/imports/${batch.id}/confirm`,{headers})).status()).toBe(200);
 const students=await(await page.request.get('/api/students')).json();const student=students.items.find((s:{student_number:string})=>s.student_number==='COMPARE-SYN-14');expect(student).toBeTruthy();
 await page.getByRole('button',{name:'论文上传与解析',exact:true}).click();await page.getByLabel('绑定学生ID').fill(String(student.id));await page.getByLabel('标题',{exact:true}).fill('合成论文闭环');await page.getByLabel('文件涉及全体学生ID（JSON数组）').fill(JSON.stringify([student.id]));await page.getByLabel('论文PDF').setInputFiles({name:'synthetic.pdf',mimeType:'application/pdf',buffer:Buffer.from('synthetic damaged PDF')});await page.getByRole('button',{name:'上传新版本并排队'}).click();await expect(page.getByText('文件损坏或不可用',{exact:false})).toBeVisible();
 const papers=(await(await page.request.get('/api/papers')).json()).items;const paper=papers.find((p:{student_id:number})=>p.student_id===student.id);
 await page.getByLabel('比较论文版本ID').fill(String(paper.id));await page.getByRole('button',{name:'读取标签历史'}).click();
 await page.getByLabel('样本标签',{exact:true}).selectOption('优秀');await page.getByLabel('业务确认人').fill('合成专家14');await page.getByLabel('确认依据').fill('合成确认书14');await page.getByRole('button',{name:'保存标签新版本'}).click();await expect(page.getByText('合成确认书14',{exact:false})).toBeVisible();
 await page.getByRole('button',{name:'生成同类比较'}).click();await expect(page.getByText('信息不足或缺少同类对照组，不自动跨学科比较。',{exact:false})).toBeVisible();
 await page.getByRole('button',{name:'检查历史比较是否过时'}).click();


 } finally {if(original)await grants(original);}
});
