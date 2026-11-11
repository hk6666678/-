import { test, expect } from "@playwright/test";
test("basic Excel preview then confirmed archive", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page
    .getByLabel("密码", { exact: true })
    .fill("Synthetic-password-123!");
  await page.getByRole("button", { name: "登录平台" }).click();
  await expect(page.getByRole('heading',{name:'欢迎回到工作台'})).toBeVisible();
  const session = await (await page.request.get("/api/me")).json();
  const grants = ["maintain", "view", "identity"].map((operation) => ({
    category: "basic",
    operation,
    college: "合成学院",
    major: "合成专业",
  }));
  const given = await page.request.put(`/api/users/${session.user.id}/grants`, {
    headers: { "X-CSRF-Token": session.csrf_token },
    data: {
      expected_version: session.user.version,
      request_id: crypto.randomUUID(),
      grants,
    },
  });
  expect(given.status()).toBe(200);
  const template = await page.request.get("/api/templates/basic?sample=true");
  expect(template.status()).toBe(200);
  await page.getByRole("button", { name: "基础导入与学生档案" }).click();
  await page.getByLabel("来源部门").fill("合成数据源");
  await page
    .getByLabel("基础信息 Excel")
    .setInputFiles({
      name: "synthetic-basic.xlsx",
      mimeType:
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      buffer: await template.body(),
    });
  await page.getByRole("button", { name: "上传并预览" }).click();
  await expect(page.getByText("ready: 1 / invalid: 1")).toBeVisible();
  await page.getByRole("button", { name: "确认导入有效行" }).click();
  await expect(page.getByText(/imported: 1/)).toBeVisible();
  await page.getByRole("button", { name: "查询学生档案" }).click();
  await expect(page.getByRole("button", { name: "查看来源" })).toBeVisible();
  await page.getByRole("button", { name: "查看来源" }).click();
  await expect(page.locator("pre")).toContainText("original_row");
});
