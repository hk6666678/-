import {test,expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
const python='D:/AQP-PGS/.venv/Scripts/python.exe';
test('blind review keyword quotes appear only when requested',async({page})=>{
 await page.goto('/');await page.getByLabel('用户名',{exact:true}).fill('synthetic-admin');await page.getByLabel('密码',{exact:true}).fill('Synthetic-password-123!');await page.getByRole('button',{name:'登录平台'}).click();await expect(page.getByRole('heading',{name:'Agent 智能问答'})).toBeVisible();
 const session=await(await page.request.get('/api/me')).json();const headers={'X-CSRF-Token':session.csrf_token};
 const originalGrants=await(await page.request.get('/api/access/grants')).json();
 try {
  const grants=['basic','papers','blind_reviews'].flatMap(category=>['maintain','view','identity'].map(operation=>({category,operation,college:'合成学院',major:'合成专业'})));
  grants.push({category:'blind_reviews',operation:'download',college:'合成学院',major:'合成专业'});
  expect((await page.request.put(`/api/users/${session.user.id}/grants`,{headers,data:{expected_version:session.user.version,request_id:crypto.randomUUID(),grants}})).status()).toBe(200);
  const template=await page.request.get('/api/templates/basic?sample=true');
  const basic=await(await page.request.post('/api/imports/basic/preview',{headers,multipart:{source_department:'合成来源',file:{name:'basic.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:execFileSync(python,["-c","import sys,io;from openpyxl import load_workbook;w=load_workbook(io.BytesIO(sys.stdin.buffer.read()));w.active.cell(3,1,'SYN-QUOTE-ONLY');w.active.cell(3,2,'原句合成学生');b=io.BytesIO();w.save(b);sys.stdout.buffer.write(b.getvalue())"],{input:await template.body(),env:{...process.env,PYTHONUTF8:"1"}})}}})).json();
  expect((await page.request.post(`/api/imports/${basic.id}/confirm`,{headers})).status()).toBe(200);
  const studentId=(await(await page.request.get('/api/students')).json()).items.find((s:{student_number?:string})=>s.student_number==='SYN-QUOTE-ONLY').id;
  const pdf=execFileSync(python,['-c',"import sys;from pypdf import PdfWriter;w=PdfWriter();w.add_blank_page(width=72,height=72);w.write(sys.stdout.buffer)"]);
  const paper=await(await page.request.post('/api/papers',{headers,multipart:{student_id:String(studentId),title:'合成论文',expected_version:'0',covered_student_ids:JSON.stringify([studentId]),file:{name:'synthetic.pdf',mimeType:'application/pdf',buffer:pdf}}})).json();
  const review=await page.request.post('/api/external-assessments',{headers,data:{category:'blind_reviews',paper_version_id:paper.id,batch:'合成批次',anonymous_code:'Q01',scores:{quality:85},comment:'论文创新性较强。写作规范有待改进。',source:'合成来源'}});
  expect(review.status()).toBe(200);
  await page.getByRole('button',{name:'盲审与答辩',exact:true}).click();
  await page.getByText('盲审意见关键词统计',{exact:true}).click();
  await page.getByLabel('关键词（逗号分隔）').fill('创新,写作规范');
  const showQuotes=page.getByLabel('同时列出命中这些关键词的评语原句');
  await expect(showQuotes).toBeChecked();
  await page.getByRole('button',{name:'统计关键词',exact:true}).click();
  const quotes=page.getByRole('region',{name:'关键词命中的评语原句'});
  // 共享套件库里可能有其他用例的评语，因此只断言本用例的两句各自出现，不断言总行数。
  await expect(quotes.getByRole('cell',{name:'论文创新性较强。',exact:true}).first()).toBeVisible();
  await expect(quotes.getByRole('cell',{name:'写作规范有待改进。',exact:true}).first()).toBeVisible();
  await expect(quotes.getByRole('row').filter({hasText:`评语 #${(await review.json()).id}`})).toHaveCount(2);
  await showQuotes.uncheck();
  await page.getByRole('button',{name:'统计关键词',exact:true}).click();
  await expect(page.getByRole('heading',{name:'关键词命中的评语原句'})).toHaveCount(0);
  await expect(page.getByRole('listitem').filter({hasText:'创新 · 1 次'})).toBeVisible();
 } finally {
  const latest=await(await page.request.get('/api/me')).json();
  await page.request.put(`/api/users/${latest.user.id}/grants`,{headers,data:{expected_version:latest.user.version,request_id:crypto.randomUUID(),grants:originalGrants}});
 }
});
