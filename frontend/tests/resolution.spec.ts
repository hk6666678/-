import { readFileSync } from "node:fs";
import { test, expect } from "@playwright/test";
test("synthetic basic error is corrected with evidence and second confirmation", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page
    .getByLabel("密码", { exact: true })
    .fill("Synthetic-password-123!");
  await page.getByRole("button", { name: "登录平台" }).click();
  await page
    .getByRole("button", { name: "数据纠错与维护", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "在线纠错与身份确认" }),
  ).toBeVisible();
  const session = await (await page.request.get("/api/me")).json();
  const headers = { "X-CSRF-Token": session.csrf_token };
  const original = await (
    await page.request.get(`/api/users/${session.user.id}/grants`)
  ).json();
  try {
    await page.request.put(`/api/users/${session.user.id}/grants`, {
      headers,
      data: {
        expected_version: session.user.version,
        request_id: crypto.randomUUID(),
        grants: ["maintain", "identity", "export"].map((operation) => ({
          category: "basic",
          operation,
          college: "示例学院",
          major: "计算机",
        })),
      },
    });
    const b = await (
      await page.request.post("/api/imports/basic/preview", {
        headers,
        multipart: {
          source_department: "合成",
          file: {
            name: "synthetic.xlsx",
            mimeType:
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            buffer: Buffer.from(
              readFileSync("tests/resolution-synthetic.base64", "utf8"),
              "base64",
            ),
          },
        },
      })
    ).json();
    await page.getByLabel("待处理批次编号").fill(String(b.id));
    await page.getByRole("button", { name: "查看待处理记录" }).click();
    await page.getByRole("button", { name: /第4行/ }).click();
    await page.getByLabel("姓名", { exact: true }).fill("合成修复");
    await page.getByLabel("人工核实依据").fill("合成学籍清单人工核实");
    await page.getByRole("button", { name: "保存并重新校验" }).click();
    await expect(page.getByText(/校验版本1：ready/)).toBeVisible();
    await page.getByRole("button", { name: "再次确认此修复行入库" }).click();
    await expect(
      page.getByRole("button", { name: /第4行 · imported/ }),
    ).toBeVisible();
  } finally {
    const current = await (await page.request.get("/api/me")).json();
    await page.request.put(`/api/users/${session.user.id}/grants`, {
      headers,
      data: {
        expected_version: current.user.version,
        request_id: crypto.randomUUID(),
        grants: original.grants,
      },
    });
  }
});
