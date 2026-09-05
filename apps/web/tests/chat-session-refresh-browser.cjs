// Browser plugin not available; validate with local Playwright and delayed mock sessions.
const { chromium, expect } = require("@playwright/test");
const assert = require("node:assert/strict");
const base = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000";
(async () => {
 const browser = await chromium.launch();
 try {
  for (const authenticated of [true, false]) {
   const context = await browser.newContext({ locale: "en-US" });
   await context.addInitScript(() => {
    for (const key of ["localStorage", "sessionStorage"]) Object.defineProperty(window, key, { get() { throw Error("Web Storage forbidden"); } });
    window.__guestFlashes = 0;
    new MutationObserver(() => {
     if (document.querySelector(".session-pending-shell") && document.querySelector(".chat-auth-login, .chat-auth-signup, nav[aria-label='Menu tamu']")) window.__guestFlashes++;
    }).observe(document, { childList: true, subtree: true });
   });
   let release;
   let arrived;
   let gate;
   const reset = () => { gate = new Promise(resolve => { release = resolve; }); return new Promise(resolve => { arrived = resolve; }); };
   let requested = reset();
   await context.route("**/*", async route => {
    const url = new URL(route.request().url());
    if (url.origin !== new URL(base).origin) return route.abort();
    if (url.pathname === "/api/backend/auth/session") {
     arrived(); await gate;
     return route.fulfill({ status: authenticated ? 200 : 401, json: authenticated ? { user: { user_id: "refresh-user", email: "refresh@example.test", name: "Refresh User", roles: ["user"] } } : {} });
    }
    if (url.pathname.startsWith("/api/backend/auth/")) return route.fulfill({ status: 401, json: {} });
    if (url.pathname.startsWith("/api/backend/")) return route.fulfill({ json: [] });
    return route.continue();
   });
   const page = await context.newPage();
   const errors = [];
   page.on("pageerror", error => errors.push(error.message));
   for (const refresh of [false, true]) {
    if (refresh) requested = reset();
    if (refresh) await page.reload({ waitUntil: "domcontentloaded" });
    else await page.goto(base + "/chat", { waitUntil: "domcontentloaded" });
    await requested;
    await expect(page.locator(".session-pending-shell")).toBeVisible();
    await expect(page.locator("header[aria-busy='true']")).toBeVisible();
    await expect(page.locator(".chat-auth-login, .chat-auth-signup")).toHaveCount(0);
    await expect(page.getByRole("navigation", { name: "Menu tamu", exact: true })).toHaveCount(0);
    assert.equal(await page.evaluate(() => window.__guestFlashes), 0);
    release();
    await expect(page.locator(authenticated ? ".authenticated-shell" : ".guest-shell")).toBeVisible();
    if (authenticated) {
     await expect(page.getByText("Refresh User", { exact: true }).first()).toBeVisible();
     await expect(page.locator(".chat-auth-login, .chat-auth-signup")).toHaveCount(0);
    } else await expect(page.locator(".chat-auth-login")).toBeVisible();
    assert.equal(await page.evaluate(() => window.__guestFlashes), 0);
   }
   assert.deepEqual(errors, []);
   console.log(`PASS ${authenticated ? "logged-in" : "guest"} initial load and refresh: no premature guest UI`);
   await context.close();
  }
 } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
