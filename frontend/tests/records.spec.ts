import { readFileSync } from "node:fs";
import { test, expect } from "@playwright/test";
test("synthetic formal correction and void preserve history", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page
    .getByLabel("密码", { exact: true })
    .fill("Synthetic-password-123!");
  await page.getByRole("button", { name: "登录平台" }).click();
  await expect(
    page.getByRole("heading", { name: "正式记录更正与历史" }),
  ).toBeVisible();
  const s = await (await page.request.get("/api/me")).json(),
    headers = { "X-CSRF-Token": s.csrf_token },
    url = `/api/users/${s.user.id}/grants`;
  const original = await (await page.request.get(url)).json();
  try {
    expect(
      (
        await page.request.put(url, {
          headers,
          data: {
            expected_version: s.user.version,
            request_id: crypto.randomUUID(),
            grants: ["maintain", "view", "identity", "void"].map(
              (operation) => ({
                category: "basic",
                operation,
                college: "示例学院",
                major: "计算机",
              }),
            ),
          },
        })
      ).ok(),
    ).toBeTruthy();

    const b = await (
      await page.request.post("/api/imports/basic/preview", {
        headers,
        multipart: {
          source_department: "合成更正来源",
          file: {
            name: "synthetic.xlsx",
            mimeType:
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            buffer: Buffer.from(
              readFileSync("tests/records-synthetic.base64", "utf8"),
              "base64",
            ),
          },
        },
      })
    ).json();
    expect(
      (
        await page.request.post(`/api/imports/${b.id}/confirm`, { headers })
      ).ok(),
    ).toBeTruthy();
    const records = await (await page.request.get("/api/records/basic")).json();
    const own = records.items.find(
      (r: { current: Record<string, string> }) =>
        r.current["学号"] === "SYNTHETIC-07001",
    );
    expect(own).toBeTruthy();
    await page.getByRole("button", { name: "加载正式记录" }).click();
    await page
      .getByRole("button", {
        name: `记录${own.id} · 版本1 · 有效`,
        exact: true,
      })
      .click();
    await page.getByLabel("研究方向", { exact: true }).fill("合成更正方向");
    await page.getByLabel("更正或作废依据").fill("合成人工核实");
    await page.getByRole("button", { name: "预览新旧差异" }).click();
    await expect(page.getByLabel("新旧差异")).toContainText("合成更正方向");
    await page.getByRole("button", { name: "确认此更正" }).click();
    await expect(page.getByText(/版本2 · correct/)).toBeVisible();
    await page.getByLabel("更正或作废依据").fill("合成作废依据");
    await page.getByRole("button", { name: "确认按原因作废" }).click();
    await expect(page.getByText(/版本3 · void/)).toBeVisible();
  } finally {
    const c = await (await page.request.get("/api/me")).json();
    await page.request.put(url, {
      headers,
      data: {
        expected_version: c.user.version,
        request_id: crypto.randomUUID(),
        grants: original.grants,
      },
    });
  }
});
