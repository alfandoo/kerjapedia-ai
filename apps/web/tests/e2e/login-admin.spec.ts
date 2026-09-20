import { expect, test } from "@playwright/test";

test("unauthenticated admin routes redirect to the admin login", async ({ page }) => {
  await page.goto("/admin/dashboard");
  await expect(page).toHaveURL(/\/login-admin$/);

  await page.goto("/admin/");
  await expect(page).toHaveURL(/\/login-admin$/);
  await expect(page.getByRole("heading", { name: "Masuk sebagai admin" })).toBeVisible();
});
test("admin login keeps a clear path back to chat", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 768 });
  await page.goto("/login-admin");

  await expect(page.getByRole("heading", { name: "Masuk sebagai admin" })).toBeVisible();
  await expect(page.locator("img[src*='admin-legal-library.png']")).toBeVisible();
  await expect(page.getByRole("link", { name: "Kembali ke chat" })).toHaveAttribute(
    "href",
    "/chat"
  );

  const layout = page.locator("main > div");
  await expect
    .poll(async () => (await layout.boundingBox())?.height ?? Infinity)
    .toBeLessThanOrEqual(560);
  const layoutBox = await layout.boundingBox();
  expect(layoutBox).not.toBeNull();
  expect(Math.abs(layoutBox!.y - (768 - layoutBox!.height) / 2)).toBeLessThanOrEqual(1);

  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollHeight))
    .toBeLessThanOrEqual(768);

  await page.setViewportSize({ width: 390, height: 667 });
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollHeight))
    .toBeLessThanOrEqual(667);
});
