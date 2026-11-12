import { expect, request as playwrightRequest, test } from "@playwright/test";
import { execFileSync } from "node:child_process";

test("synthetic Excel report and originals use independent current grants", async ({
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

  const api = await playwrightRequest.newContext({
    baseURL: new URL(page.url()).origin,
    storageState: await page.context().storageState(),
  });
  const session = await (await api.get("/api/me")).json();
  const headers = { "X-CSRF-Token": session.csrf_token };
  const original = (
    await (await api.get(`/api/users/${session.user.id}/grants`)).json()
  ).grants;

  async function grants(operations: string[] | null) {
    const current = await (await api.get("/api/me")).json();
    const response = await api.put(`/api/users/${session.user.id}/grants`, {
      headers,
      data: {
        expected_version: current.user.version,
        request_id: crypto.randomUUID(),
        grants: operations
          ? ["basic", "courses"].flatMap((category) =>
              operations.map((operation) => ({
                category,
                operation,
                college: "导出19合成学院",
                major: "导出19合成专业",
              })),
            )
          : original,
      },
    });
    expect(response.status()).toBe(200);
    await response.dispose();
  }

  try {
    await grants(["maintain", "view", "analyze", "export"]);
    const bytes = execFileSync(
      "../.venv/Scripts/python.exe",
      [
        "-c",
        "import io,sys;from openpyxl import Workbook;w=Workbook();s=w.active;s.append(['AQP-PGS','basic','1']);s.append(['学号','姓名','所属学院','专业','培养层次','入学年份']);s.append(['SYN-EXPORT-19','合成导出学生','导出19合成学院','导出19合成专业','硕士','2025']);o=io.BytesIO();w.save(o);sys.stdout.buffer.write(o.getvalue())",
      ],
      { env: { ...process.env, PYTHONUTF8: "1" } },
    );
    const imported = await (
      await api.post("/api/imports/basic/preview", {
        headers,
        multipart: {
          source_department: "合成来源",
          file: {
            name: "synthetic.xlsx",
            mimeType:
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            buffer: bytes,
          },
        },
      })
    ).json();

    const basicConfirmed = await api.post(
      `/api/imports/${imported.id}/confirm`,
      {
        headers,
      },
    );
    expect(basicConfirmed.status()).toBe(200);
    await basicConfirmed.dispose();
    const courseBytes = execFileSync(
      "../.venv/Scripts/python.exe",
      [
        "-c",
        "import io,sys;from openpyxl import Workbook;w=Workbook();s=w.active;s.append(['AQP-PGS','courses','1']);s.append(['学号','姓名','课程编号','课程名称','修读学期','考核次数','评分制度','原始成绩','业务通过结果','学分']);s.append(['SYN-EXPORT-19','合成导出学生','EXPORT-C19','合成课程','2025秋',1,'百分制',80,'通过',2]);o=io.BytesIO();w.save(o);sys.stdout.buffer.write(o.getvalue())",
      ],
      { env: { ...process.env, PYTHONUTF8: "1" } },
    );
    const courseImported = await (
      await api.post("/api/imports/courses/preview", {
        headers,
        multipart: {
          source_department: "合成来源",
          file: {
            name: "synthetic.xlsx",
            mimeType:
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            buffer: courseBytes,
          },
        },
      })
    ).json();
    const courseConfirmed = await api.post(
      `/api/imports/courses/${courseImported.id}/confirm`,
      { headers },
    );
    expect(courseConfirmed.status()).toBe(200);
    await courseConfirmed.dispose();

    const deniedOriginal = await api.get(
      `/api/imports/${imported.id}/download`,
    );
    expect(deniedOriginal.status()).toBe(403);
    await deniedOriginal.dispose();

    await page
      .getByRole("button", { name: "课程统计与通过规则", exact: true })
      .click();
    const scope = page.locator("section").filter({
      has: page.getByRole("heading", {
        name: "课程分析与通过规则",
        exact: true,
      }),
    });
    await scope.getByLabel("学院", { exact: true }).fill("导出19合成学院");
    await scope.getByLabel("专业", { exact: true }).fill("导出19合成专业");
    await scope.getByRole("button", { name: "生成新分析版本" }).click();
    const link = scope.getByRole("link", {
      name: "下载分析 Excel（须导出权限）",
    });
    await expect(link).toBeVisible();

    const [download] = await Promise.all([
      page.waitForEvent("download"),
      link.click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/analysis-\d+\.xlsx/);
    const file = test.info().outputPath(download.suggestedFilename());
    await download.saveAs(file);
    execFileSync(
      "../.venv/Scripts/python.exe",
      [
        "-c",
        "import sys;from openpyxl import load_workbook;w=load_workbook(sys.argv[1]);v=[c.value for s in w for r in s for c in r];missing={'generated_at','stale','导出19合成学院'}-set(v);assert not missing, missing",
        file!,
      ],
      { env: { ...process.env, PYTHONUTF8: "1" } },
    );

    await grants(["download", "identity"]);
    const deniedExport = await api.get((await link.getAttribute("href"))!);
    expect(deniedExport.status()).toBe(403);
    await deniedExport.dispose();

    scope.getByText("来源下钻与逐条证据", { exact: true }).click();
    const [originalDownload] = await Promise.all([
      page.waitForEvent("download"),
      scope
        .getByRole("link", { name: "下载原始 Excel（全文件范围及身份授权）" })
        .click(),
    ]);
    expect(originalDownload.suggestedFilename()).toMatch(/import-\d+\.xlsx/);

    const allowedOriginal = await api.get(
      `/api/imports/${imported.id}/download`,
    );
    expect(allowedOriginal.status()).toBe(200);
    await allowedOriginal.dispose();
  } finally {
    await grants(null);
    const restored = await (
      await api.get(`/api/users/${session.user.id}/grants`)
    ).json();
    expect(restored.grants).toEqual(original);
    await api.dispose();
  }
});
