import { test, expect } from "@playwright/test";
test("milestone pending import with missing score and attachment", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page
    .getByLabel("密码", { exact: true })
    .fill("Synthetic-password-123!");
  await page.getByRole("button", { name: "登录平台" }).click();
  await expect(
    page.getByRole("heading", { name: "欢迎回到工作台" }),
  ).toBeVisible();
  const session = await (await page.request.get("/api/me")).json();
  const grants = ["maintain", "view", "identity"].map((operation) => ({
    category: "topic",
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
  const template = await page.request.get(
    "/api/templates/milestones/topic?sample=true",
  );
  expect(template.status()).toBe(200);
  await page.getByRole("button", { name: "选题与中期导入" }).click();
  await page.getByLabel("来源部门").fill("合成数据源");
  await page.getByLabel("来源学院").fill("合成学院");
  await page.getByLabel("来源专业").fill("合成专业");
  await page.getByLabel("选题与中期 Excel").setInputFiles({
    name: "synthetic-basic.xlsx",
    mimeType:
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: await template.body(),
  });
  await page.getByRole("button", { name: "上传并预览" }).click();
  await expect(page.getByText("pending: 1 / invalid: 1")).toBeVisible();
  await page.getByRole("button", { name: "确认导入有效行" }).click();
  await expect(page.getByText(/pending: 1/)).toBeVisible();
});
