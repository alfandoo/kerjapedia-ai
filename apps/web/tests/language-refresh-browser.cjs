// Browser plugin not available; validate using the repository Playwright runtime.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const base = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000";
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ locale: "id-ID" });
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
      for (const name of ["localStorage", "sessionStorage"]) Object.defineProperty(window, name, { get() { throw new Error("Web Storage forbidden"); } });
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(base);
    await page.getByRole("button", { name: "Pengaturan", exact: true }).click();
    await page.locator('[aria-controls="settings-language-options"]').click();
    await page
      .locator("#settings-language-options")
      .getByRole("button", { name: "English", exact: true })
      .click();
    assert.equal(await page.locator("html").getAttribute("lang"), "en");
    assert.equal((await context.cookies()).find((c) => c.name === "settings-language").value, "en");
    await page.reload();
    await page.getByRole("heading", { name: "What would you like to understand?" }).waitFor();
    assert.equal(await page.locator("html").getAttribute("lang"), "en");
    console.log("PASS setting English persists across refresh");
    const noJs = await browser.newContext({ javaScriptEnabled: false, locale: "id-ID" });
    await noJs.addCookies(await context.cookies());
    const serverPage = await noJs.newPage();
    await serverPage.goto(base);
    await serverPage.getByRole("heading", { name: "What would you like to understand?" }).waitFor();
    assert.equal(await serverPage.locator("html").getAttribute("lang"), "en");
    console.log("PASS server HTML is English without JavaScript on Indonesian browser");
    await noJs.close();
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    await page.locator('[aria-controls="settings-language-options"]').click();
    await page
      .locator("#settings-language-options")
      .getByRole("button", { name: "Indonesia", exact: true })
      .click();
    await page.reload();
    await page.getByRole("heading", { name: "Apa yang ingin Anda pahami?" }).waitFor();
    assert.equal(await page.locator("html").getAttribute("lang"), "id");
    console.log("PASS switching back to Indonesian persists");
    assert.deepEqual(errors, []);
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
