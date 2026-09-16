// Browser plugin not available; use the repository Playwright runtime.
const { chromium, expect } = require("@playwright/test");
const assert = require("node:assert/strict");
const base = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000";
(async () => {
  const browser = await chromium.launch();
  try {
    const context = await browser.newContext({ locale: "id-ID", colorScheme: "light" });
    await context.route("**/*", (route) => {
      const url = new URL(route.request().url());
      if (url.origin !== new URL(base).origin) return route.abort();
      if (url.pathname.startsWith("/api/backend/"))
        return route.fulfill({
          status: url.pathname.includes("/auth/") ? 401 : 200,
          contentType: "application/json",
          body: url.pathname.includes("/auth/") ? "{}" : "[]",
        });
      return route.continue();
    });
    await context.addInitScript(() => {
      for (const name of ["localStorage", "sessionStorage"])
        Object.defineProperty(window, name, {
          get() {
            throw new Error("Web Storage forbidden");
          },
        });
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.stack));
    async function choose(theme) {
      await page.getByRole("button", { name: "Pengaturan", exact: true }).click();
      await page.locator('[aria-controls="settings-appearance-options"]').click();
      await page
        .locator("#settings-appearance-options")
        .getByRole("button", { name: theme, exact: true })
        .click();
    }
    await page.goto(base);
    for (const theme of ["Dark", "Light"]) {
      await choose(theme);
      const value = theme.toLowerCase();
      await expect(page.locator("html")).toHaveAttribute("data-theme", value);
      await page.reload();
      await expect(page.locator("html")).toHaveAttribute("data-theme", value);
      assert.equal((await context.cookies()).find((c) => c.name === "settings-theme").value, value);
      const noJs = await browser.newContext({ javaScriptEnabled: false });
      await noJs.addCookies(await context.cookies());
      const raw = await noJs.newPage();
      await raw.goto(base);
      await expect(raw.locator("html")).toHaveClass(new RegExp(value));
      await expect(raw.locator("html")).toHaveAttribute("data-theme", value);
      await noJs.close();
      console.log(`PASS ${theme} refresh and server HTML without JavaScript`);
    }
    await choose("System");
    await page.emulateMedia({ colorScheme: "dark" });
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.emulateMedia({ colorScheme: "light" });
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    console.log("PASS System follows device changes and refresh");
    assert.deepEqual(errors, []);
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
