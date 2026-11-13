import { readFileSync } from "node:fs";
import { test, expect } from "@playwright/test";
test("mentor directories relationships facts and revocation", async ({
  page,
}) => {
  test.setTimeout(90000);
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
  const headers = { "X-CSRF-Token": session.csrf_token };
  const grants = ["basic", "mentor_groups"].flatMap((category) =>
    ["maintain", "view", "identity", "analyze"].map((operation) => ({
      category,
      operation,
      college: "合成学院",
      major: "合成专业",
    })),
  );
  expect(
    (
      await page.request.put(`/api/users/${session.user.id}/grants`, {
        headers,
        data: {
          expected_version: session.user.version,
          request_id: crypto.randomUUID(),
          grants,
        },
      })
    ).status(),
  ).toBe(200);
  const batch = await (
    await page.request.post("/api/imports/basic/preview", {
      headers,
      multipart: {
        source_department: "Synthetic",
        file: {
          name: "synthetic.xlsx",
          mimeType:
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          buffer: Buffer.from(
            readFileSync("tests/basic-synthetic.base64", "utf8"),
            "base64",
          ),
        },
      },
    })
  ).json();
  expect(
    (
      await page.request.post(`/api/imports/${batch.id}/confirm`, { headers })
    ).status(),
  ).toBe(200);
  const student = (await (await page.request.get("/api/students")).json())
    .items[0];
  await page.getByRole("button", { name: "导师与课题组", exact: true }).click();
  for (const [kind, number, name] of [
    ["mentors", "SYN-MENTOR-1", "合成导师"],
    ["groups", "SYN-GROUP-1", "合成课题组"],
  ]) {
    await page
      .getByRole("combobox", { name: "目录类型", exact: true })
      .selectOption(kind);
    await page.getByLabel("目录业务编号", { exact: true }).fill(number);
    await page.getByLabel("目录名称", { exact: true }).fill(name);
    await page.getByLabel("目录学院", { exact: true }).fill("合成学院");
    await page.getByLabel("目录专业", { exact: true }).fill("合成专业");
    await page.getByRole("button", { name: "保存目录", exact: true }).click();
    await expect(page.getByRole("status")).toContainText("目录已保存");
  }
  await page
    .getByRole("combobox", { name: "关系学生", exact: true })
    .selectOption(String(student.id));
  await page
    .getByRole("combobox", { name: "业务导师", exact: true })
    .selectOption({ label: "合成导师" });
  await page
    .getByRole("combobox", { name: "业务课题组", exact: true })
    .selectOption({ label: "合成课题组" });
  await page.getByLabel("关系开始日期", { exact: true }).fill("2025-09-01");
  await page.getByLabel("关系来源部门", { exact: true }).fill("合成培养办");
  await page
    .getByLabel("关系变更依据", { exact: true })
    .fill("Synthetic initial relationship");
  await page.getByRole("button", { name: "保存学生关系", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("关系已保存");
  await page
    .getByRole("heading", { name: "导师与课题组", level: 2 })
    .scrollIntoViewIfNeeded();
  await page.screenshot({ path: "test-results/mentor-groups-directory.png" });
  await page
    .getByRole("heading", { name: "学生关系与历史", exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({ path: "test-results/mentor-groups-relations.png" });
  await page.getByRole("button", { name: /关系历史 \d+/ }).click();
  await expect(
    page.getByRole("heading", { name: "关系版本历史" }),
  ).toBeVisible();
  await page.getByLabel("关系统计日期", { exact: true }).fill("2026-01-01");
  await page.getByRole("button", { name: "查询关系事实", exact: true }).click();
  await expect(page.getByLabel("关系事实结果")).toContainText("去重学生数：1");
  await page
    .getByRole("button", { name: "科研论文查看明细", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "科研论文事实证据" }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/mentor-groups-facts.png",
    fullPage: true,
  });
  const current = await (
    await page.request.get(`/api/users/${session.user.id}/grants`)
  ).json();
  expect(
    (
      await page.request.put(`/api/users/${session.user.id}/grants`, {
        headers,
        data: {
          expected_version: current.version,
          request_id: crypto.randomUUID(),
          grants: [],
        },
      })
    ).status(),
  ).toBe(200);
  await page
    .getByRole("button", { name: "刷新当前授权范围", exact: true })
    .click();
  await expect(page.getByRole("button", { name: /关系历史 \d+/ })).toHaveCount(
    0,
  );
  await page.getByRole("button", { name: "查询关系事实", exact: true }).click();
  await expect(page.getByLabel("关系事实结果")).toContainText("去重学生数：0");
});

