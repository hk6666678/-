import {test,expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
const python='D:/AQP-PGS/.venv/Scripts/python.exe';
test('assessment Excel error correction and confirmation',async({page})=>{
 await page.goto('/');await page.getByLabel('用户名',{exact:true}).fill('synthetic-admin');await page.getByLabel('密码',{exact:true}).fill('Synthetic-password-123!');await page.getByRole('button',{name:'登录平台'}).click();await expect(page.getByRole('heading',{name:'欢迎回到工作台'})).toBeVisible();
 const session=await(await page.request.get('/api/me')).json();const headers={'X-CSRF-Token':session.csrf_token};
 expect((await page.request.put(`/api/users/${session.user.id}/grants`,{headers,data:{expected_version:session.user.version,request_id:crypto.randomUUID(),grants:['basic','papers','blind_reviews'].flatMap(category=>['maintain','view','identity'].map(operation=>({category,operation,college:'合成学院',major:'合成专业'})))}})).status()).toBe(200);
 const template=await page.request.get('/api/templates/basic?sample=true');
 const basic=await(await page.request.post('/api/imports/basic/preview',{headers,multipart:{source_department:'合成来源',file:{name:'basic.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:await template.body()}}})).json();
 expect((await page.request.post(`/api/imports/${basic.id}/confirm`,{headers})).status()).toBe(200);
 const pdf=execFileSync(python,['-c',"import sys;from pypdf import PdfWriter;w=PdfWriter();w.add_blank_page(width=72,height=72);w.write(sys.stdout.buffer)"]);
 const paper=await(await page.request.post('/api/papers',{headers,multipart:{student_id:'1',title:'合成论文',expected_version:'0',covered_student_ids:'[1]',file:{name:'synthetic.pdf',mimeType:'application/pdf',buffer:pdf}}})).json();
 function workbook(score:number){return execFileSync(python,['-c',`import sys,io;from openpyxl import Workbook;w=Workbook();s=w.active;s.append(['category','paper_version_id','batch','anonymous_code','template_version','scores','comment','source']);s.append(['blind_reviews',${paper.id},'合成批次','R01','simulation-v1','{"quality":${score}}','合成意见','合成来源']);b=io.BytesIO();w.save(b);sys.stdout.buffer.write(b.getvalue())`]);}
 await page.getByRole('button',{name:'盲审与答辩',exact:true}).click();
 await page.getByLabel('标准Excel文件').setInputFiles({name:'bad.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:workbook(101)});await page.getByRole('button',{name:'上传并预览'}).click();await expect(page.getByRole('cell',{name:'分项成绩与模板或评分范围不匹配',exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'确认导入本批次'})).toBeDisabled();
 await page.screenshot({path:'test-results/assessment-error.png',fullPage:true});
 await page.getByLabel('标准Excel文件').setInputFiles({name:'good.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:workbook(85)});await page.getByRole('button',{name:'上传并预览'}).click();await expect(page.getByRole('button',{name:'确认导入本批次'})).toBeEnabled();await page.getByRole('button',{name:'确认导入本批次'}).click();await expect(page.getByRole('status')).toHaveText('批次已确认');await expect(page.getByRole('cell',{name:'R01',exact:true})).toBeVisible();await page.screenshot({path:'test-results/assessment-confirmed.png',fullPage:true});
});
