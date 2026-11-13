import { test, expect } from "@playwright/test";
test("simulation rule draft and independently confirmed activation", async ({
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
  expect(
    (
      await page.request.put(`/api/users/${session.user.id}/grants`, {
        headers: { "X-CSRF-Token": session.csrf_token },
        data: {
          expected_version: session.user.version,
          request_id: crypto.randomUUID(),
          grants: [
            "maintain",
            "view",
            "identity",
            "analyze",
            "activate_evaluation",
          ].map((operation) => ({
            category: "talent_evaluation",
            operation,
            college: "合成学院",
            major: "合成专业",
          })),
        },
      })
    ).status(),
  ).toBe(200);
  await page
    .getByRole("button", { name: "人才指标模拟评价", exact: true })
    .click();
  await page.getByLabel("规则名称", { exact: true }).fill("合成演示规则");
  await page.getByLabel("学院", { exact: true }).fill("合成学院");
  await page.getByLabel("专业", { exact: true }).fill("合成专业");
  await page.getByRole("button", { name: "保存模拟草稿", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("尚未启用");
  await page.getByLabel("业务确认人", { exact: true }).fill("合成业务确认人");
  await page
    .getByLabel("确认依据", { exact: true })
    .fill("仅验证模拟流程，不作为真实人才标准");
  await page.getByLabel("确认仅用于模拟演示", { exact: true }).check();
  await page
    .getByRole("button", { name: "确认启用模拟规则", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("已启用模拟版本");
  await expect(
    page.getByRole("cell", { name: "模拟已启用", exact: true }),
  ).toBeVisible();
  await page.locator(".content").evaluate(el=>el.scrollTo(0,0));
  await page.screenshot({
    path: "../artifacts/full07-simulation.png",
    fullPage: true,
  });
});
