import { test, expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';
test('synthetic Excel report and originals use independent current grants', async ({page}) => {
 await page.goto('/');
 await page.getByLabel('用户名',{exact:true}).fill('synthetic-admin');
 await page.getByLabel('密码',{exact:true}).fill('Synthetic-password-123!');
 await page.getByRole('button',{name:'登录平台'}).click();
 await expect(page.getByRole('heading',{name:'欢迎回到工作台'})).toBeVisible();
 const me=await (await page.request.get('/api/me')).json();
 const headers={'X-CSRF-Token':me.csrf_token};
 const original=(await (await page.request.get(`/api/users/${me.user.id}/grants`)).json()).grants;
 async function grants(operations:string[]|null){const u=await(await page.request.get('/api/me')).json();const r=await page.request.put(`/api/users/${me.user.id}/grants`,{headers,data:{expected_version:u.user.version,request_id:crypto.randomUUID(),grants:operations?['basic','courses'].flatMap(category=>operations.map(operation=>({category,operation,college:'导出19合成学院',major:'导出19合成专业'}))):original}});expect(r.status()).toBe(200);}
 try {
  await grants(['maintain','view','analyze','export']);
  const bytes=execFileSync('../.venv/Scripts/python.exe',['-c',"import io,sys;from openpyxl import Workbook;w=Workbook();s=w.active;s.append(['AQP-PGS','basic','1']);s.append(['学号','姓名','所属学院','专业','培养层次','入学年份']);s.append(['SYN-EXPORT-19','合成导出学生','导出19合成学院','导出19合成专业','硕士','2025']);o=io.BytesIO();w.save(o);sys.stdout.buffer.write(o.getvalue())"],{env:{...process.env,PYTHONUTF8:'1'}});
  const b=await(await page.request.post('/api/imports/basic/preview',{headers,multipart:{source_department:'合成来源',file:{name:'synthetic.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:bytes}}})).json();
  expect((await page.request.get(`/api/imports/${b.id}/download`)).status()).toBe(403);
  const scope=page.locator('section').filter({has:page.getByRole('heading',{name:'课程分析与通过规则',exact:true})});
  await scope.getByLabel('学院',{exact:true}).fill('导出19合成学院');await scope.getByLabel('专业',{exact:true}).fill('导出19合成专业');
  await scope.getByRole('button',{name:'生成新分析版本'}).click();
  const link=scope.getByRole('link',{name:'下载分析 Excel（须导出权限）'});
  await expect(link).toBeVisible();
  const [download]=await Promise.all([page.waitForEvent('download'),link.click()]);
  expect(download.suggestedFilename()).toMatch(/analysis-\d+\.xlsx/);
  const file=await download.path();
  const check=execFileSync('../.venv/Scripts/python.exe',['-c',"import sys;from openpyxl import load_workbook;w=load_workbook(sys.argv[1]);v=[c.value for s in w for r in s for c in r];assert 'generated_at' in v;assert 'stale' in v;assert '导出19合成学院' in v",file!],{env:{...process.env,PYTHONUTF8:'1'}});expect(check.length).toBe(0);
  await grants(['download','identity']);
  expect((await page.request.get((await link.getAttribute('href'))!)).status()).toBe(403);
  expect((await page.request.get(`/api/imports/${b.id}/download`)).status()).toBe(200);
 } finally {await grants(null);const restored=(await(await page.request.get(`/api/users/${me.user.id}/grants`)).json()).grants;expect(restored).toEqual(original);}
});
