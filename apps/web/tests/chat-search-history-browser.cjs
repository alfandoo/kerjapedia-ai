// Browser plugin not available; use local Playwright with delayed API mocks.
const { chromium, expect } = require("@playwright/test");
const base = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000";
(async () => {
 const browser = await chromium.launch();
 try {
  const page = await browser.newPage({ locale: "en-US" });
  const rows = [{ conversation_id: "shared-history", title: "Existing account conversation", created_at: "2026-09-05T00:00:00Z", updated_at: "2026-09-05T00:00:00Z", message_count: 2 }];
  let status = 200, result = rows, gate = Promise.resolve(), release, notify;
  function delayHistory() {
   gate = new Promise(resolve => { release = resolve; });
   return new Promise(resolve => { notify = resolve; });
  }
  await page.route("**/*", async route => {
   const url = new URL(route.request().url());
   if (url.origin !== new URL(base).origin) return route.abort();
   if (url.pathname === "/api/backend/auth/session") return route.fulfill({ json: { user: { user_id: "navigation-test", name: "Navigation User", email: "test@example.test", roles: ["user"] } } });
   if (url.pathname === "/api/backend/chat/conversations") {
    notify?.(); await gate;
    return route.fulfill({ status, json: status === 200 ? result : { detail: "Mock unavailable" } });
   }
   if (url.pathname.startsWith("/api/backend/")) return route.fulfill({ json: [] });
   return route.continue();
  });
  const history = page.getByRole("button", { name: rows[0].title, exact: true });
  const empty = page.getByText("No conversations yet. Ask your first question.", { exact: true });
  await page.goto(base + "/chat");
  await expect(history).toBeVisible();
  let arrived = delayHistory();
  await page.getByRole("link", { name: "Search Regulations", exact: true }).click();
  await page.waitForURL("**/search"); await arrived;
  await expect(history).toBeVisible(); await expect(empty).toHaveCount(0);
  status = 503; release();
  await expect(page.getByText("Unable to load conversations.", { exact: true })).toBeVisible();
  await expect(history).toBeVisible(); await expect(empty).toHaveCount(0);
  console.log("PASS Chat -> Search retains history during loading and API failure");
  status = 200;
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(page.getByText("Unable to load conversations.", { exact: true })).toHaveCount(0);
  arrived = delayHistory();
  await page.getByRole("button", { name: "New chat", exact: true }).first().click();
  await page.waitForURL("**/chat"); await arrived;
  await expect(history).toBeVisible(); await expect(empty).toHaveCount(0); release();
  console.log("PASS Search -> Chat retains history while revalidating");
  arrived = delayHistory();
  await page.getByRole("link", { name: "Search Regulations", exact: true }).click();
  await page.waitForURL("**/search"); await arrived;
  await expect(empty).toHaveCount(0);
  result = []; release();
  await expect(empty).toBeVisible();
  console.log("PASS empty state only after a successful empty API response");
 } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
