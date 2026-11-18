import { test, expect } from "@playwright/test";
test("all navigation states and independent scroll", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page
    .getByLabel("密码", { exact: true })
    .fill("Synthetic-password-123!");
  await page.getByRole("button", { name: "登录平台" }).click();
  await expect(page.getByRole("heading", { name: "Agent 智能问答" })).toBeVisible();
  await page.screenshot({ path: "../artifacts/ui-polish/overview.png" });
  const nav = page.getByRole("navigation");
  await expect(nav).toBeVisible();
  for (const name of await nav.getByRole("button").allTextContents()) {
    const button = nav.getByRole("button", { name: name.trim(), exact: true });
    await button.click();
    await expect(button).toHaveAttribute("aria-current", "page");
    await expect(nav.locator('[aria-current="page"]')).toHaveCount(1);
  }
  await nav.getByRole("button").last().hover();
  expect(await nav.getByRole("button").last().evaluate(el => getComputedStyle(el).backgroundColor)).not.toBe("rgba(0, 0, 0, 0)");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Shift+Tab");
  await expect(nav.getByRole("button").last()).toBeFocused();
  expect(
    await nav
      .getByRole("button")
      .last()
      .evaluate((el) => getComputedStyle(el).outlineStyle),
  ).toBe("solid");
  const before = await page.locator("aside").boundingBox();
  await page.locator("main.content").evaluate((el) => {
    const spacer = document.createElement("div");
    spacer.id = "scroll-probe";
    spacer.style.height = "2000px";
    el.appendChild(spacer);
    el.scrollTop = 500;
  });
  expect(
    await page.locator("main.content").evaluate((el) => el.scrollTop),
  ).toBe(500);
  expect(await page.locator("aside").boundingBox()).toEqual(before);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  await nav.getByRole("button", { name: "个人账号管理", exact: true }).click();
  expect(await page.locator(".content").evaluate(el => el.scrollTop)).toBe(0);
  await expect(
    page.getByRole("heading", { name: "创建个人账号" }),
  ).toBeVisible();
  await page.locator("main.content").evaluate((el) => (el.scrollTop = 0));
  await page.locator("nav").evaluate((el) => (el.scrollTop = 0));
  await page
    .locator("main.content")
    .evaluate((el) => el.querySelector("#scroll-probe")?.remove());
  await page.screenshot({ path: "test-results/navigation-desktop.png" });
  await page.setViewportSize({ width: 375, height: 667 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(
    375,
  );
  const toggle = page.getByRole("button", { name: /展开导航/ });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await page.screenshot({ path: "../artifacts/ui-polish/navigation-mobile-closed.png" });
  await toggle.click();
  await expect(page.getByRole("button", { name: /收起导航/ })).toHaveAttribute("aria-expanded", "true");
  await page.screenshot({ path: "../artifacts/ui-polish/navigation-mobile-open.png" });
  await nav.getByRole("button", { name: "审计查询", exact: true }).click();
  await expect(page.getByRole("button", { name: /审计查询 · 展开导航/ })).toHaveAttribute("aria-expanded", "false");
  await expect(nav).toBeHidden();
});

test("mobile login error feedback", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-nonexistent-visual");
  await page.getByLabel("密码", { exact: true }).fill("Incorrect-synthetic-password!");
  await page.getByRole("button", { name: "登录平台" }).click();
  await expect(page.locator(".error")).toBeVisible();
  await page.screenshot({ path: "../artifacts/ui-polish/login-error-mobile.png" });
});
