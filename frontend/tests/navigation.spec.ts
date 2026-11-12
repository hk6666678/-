import { test, expect } from "@playwright/test";
test("all navigation states and independent scroll", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("synthetic-admin");
  await page
    .getByLabel("密码", { exact: true })
    .fill("Synthetic-password-123!");
  await page.getByRole("button", { name: "登录平台" }).click();
  const nav = page.getByRole("navigation");
  await expect(nav).toBeVisible();
  for (const name of await nav.getByRole("button").allTextContents()) {
    const button = nav.getByRole("button", { name: name.trim(), exact: true });
    await button.click();
    await expect(button).toHaveAttribute("aria-current", "page");
    await expect(nav.locator('[aria-current="page"]')).toHaveCount(1);
  }
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
    spacer.style.height = "2000px";
    el.appendChild(spacer);
    el.scrollTop = 500;
  });
  expect(
    await page.locator("main.content").evaluate((el) => el.scrollTop),
  ).toBe(500);
  expect(await page.locator("aside").boundingBox()).toEqual(before);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  await page.screenshot({ path: "test-results/navigation-desktop.png" });
  await page.setViewportSize({ width: 375, height: 667 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(
    375,
  );
  await page.screenshot({ path: "test-results/navigation-mobile.png" });
});
