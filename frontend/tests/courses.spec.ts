import { test, expect } from "@playwright/test";
test("course pending import then basic archive links original course", async ({
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
  const grants = ["basic", "courses"].flatMap((category) =>
    ["maintain", "view"].map((operation) => ({
      category,
      operation,
      college: "合成学院",
      major: "合成专业",
    })),
  );
  expect(
    (
      await page.request.put(`/api/users/${session.user.id}/grants`, {
        headers: { "X-CSRF-Token": session.csrf_token },
        data: {
          expected_version: session.user.version,
          request_id: crypto.randomUUID(),
          grants,
        },
      })
    ).status(),
  ).toBe(200);
  const file = await page.request.get("/api/templates/courses?sample=true");
  await page
    .getByRole("button", { name: "课程导入与待关联", exact: true })
    .click();
  await page.getByLabel("课程来源部门").fill("合成教务");
  await page
    .getByLabel("课程 Excel")
    .setInputFiles({
      name: "synthetic.xlsx",
      mimeType:
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      buffer: await file.body(),
    });
  await page.getByRole("button", { name: "预览课程", exact: true }).click();
  await expect(page.getByText("pending: 1", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "确认课程有效及待关联行" }).click();
  const basic = await page.request.get("/api/templates/basic?sample=true");
  const preview = await page.request.post("/api/imports/basic/preview", {
    headers: { "X-CSRF-Token": session.csrf_token },
    multipart: {
      source_department: "合成基础",
      file: {
        name: "basic.xlsx",
        mimeType:
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        buffer: await basic.body(),
      },
    },
  });
  const batch = await preview.json();
  expect(
    (
      await page.request.post(`/api/imports/${batch.id}/confirm`, {
        headers: { "X-CSRF-Token": session.csrf_token },
      })
    ).status(),
  ).toBe(200);
  await page.getByRole("button", { name: "刷新关联状态" }).click();
  await expect(page.getByText("linked: 1", { exact: true })).toBeVisible();
  await expect(page.locator("table")).not.toContainText("SYN0001");
});
