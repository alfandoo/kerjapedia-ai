// Browser plugin not available; use repository Playwright with mocked API data.
const { chromium, expect } = require("@playwright/test");
const assert = require("node:assert/strict");
const base = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000";
(async () => {
  const browser = await chromium.launch();
  try {
    const context = await browser.newContext({
      locale: "en-US",
      viewport: { width: 1584, height: 960 },
    });
    await context.addInitScript(() => {
      for (const name of ["localStorage", "sessionStorage"])
        Object.defineProperty(window, name, {
          get() {
            throw Error("Web Storage forbidden");
          },
        });
    });
    let owner = "owner-one";
    await context.route("**/*", (route) => {
      const url = new URL(route.request().url());
      if (url.origin !== new URL(base).origin) return route.abort();
      if (url.pathname === "/api/backend/auth/session")
        return route.fulfill({
          json: {
            user: {
              user_id: owner,
              name: "Test Owner",
              email: "owner@example.test",
              roles: ["user"],
            },
          },
        });
      if (url.pathname === "/api/backend/chat/conversations")
        return route.fulfill({
          json: [
            {
              conversation_id: "pin-test",
              title: "Pin persistence test",
              created_at: "2026-09-05T00:00:00Z",
              updated_at: "2026-09-05T00:00:00Z",
              message_count: 2,
            },
          ],
        });
      if (url.pathname.startsWith("/api/backend/")) return route.fulfill({ json: [] });
      return route.continue();
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(base);
    const guest = (await context.cookies()).find((c) => /kp-guest$/.test(c.name));
    assert.ok(guest?.httpOnly);
    assert.ok(!(await page.evaluate(() => document.cookie)).includes(guest.value));
    await page.getByRole("button", { name: "Pin chat", exact: true }).first().focus();
    await page.keyboard.press("Enter");
    await expect(
      page.getByRole("button", { name: "Unpin chat", exact: true }).first()
    ).toBeVisible();
    await page.reload();
    await expect(
      page.getByRole("button", { name: "Unpin chat", exact: true }).first()
    ).toBeVisible();
    assert.equal(
      (await context.cookies()).find((c) => /kp-guest$/.test(c.name)).value,
      guest.value
    );
    console.log("PASS pin survives refresh; guest cookie is stable and HttpOnly");
    owner = "owner-two";
    await page.reload();
    await expect(page.getByRole("button", { name: "Pin chat", exact: true }).first()).toBeVisible();
    owner = "owner-one";
    await page.reload();
    await page.getByRole("button", { name: "Unpin chat", exact: true }).first().focus();
    await page.keyboard.press("Enter");
    await page.reload();
    await expect(page.getByRole("button", { name: "Pin chat", exact: true }).first()).toBeVisible();
    console.log("PASS pins are scoped by account and unpin persists");
    await page.getByRole("button", { name: "Tutup sidebar", exact: true }).click();
    await page.reload();
    await expect(page.getByRole("button", { name: "Buka sidebar", exact: true })).toBeVisible();
    assert.equal(
      (await context.cookies()).find((c) => c.name === "kerjapedia.chat.sidebar.v1").value,
      "collapsed"
    );
    console.log("PASS sidebar state survives refresh with Web Storage blocked");
    assert.deepEqual(errors, []);
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
