// Browser plugin not available; use the repository Playwright installation.
const { chromium } = require("playwright");
const { spawn } = require("node:child_process");
const assert = require("node:assert/strict");
const base = "http://127.0.0.1:3103";
(async () => {
  const server = spawn(
    process.execPath,
    ["node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "3103"],
    {
      env: {
        ...process.env,
        NEXT_DIST_DIR: ".next-security-headers",
        API_INTERNAL_URL: "http://127.0.0.1:1",
        APP_ORIGIN: base,
      },
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    }
  );
  let output = "";
  server.stdout.on("data", (data) => (output += data));
  server.stderr.on("data", (data) => (output += data));
  let browser;
  try {
    let ready = false;
    for (let i = 0; i < 80; i++) {
      if (server.exitCode !== null) throw Error("Temporary server failed: " + output.slice(-1500));
      try {
        ready = (await fetch(base)).ok;
      } catch {}
      if (ready) break;
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    assert.ok(ready, "Temporary server did not start");
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    // Prevent browser smoke tests from touching real API/provider data.
    await page.route("**/*", (route) => {
      const url = new URL(route.request().url());
      if (url.origin !== base) return route.abort();
      if (url.pathname.startsWith("/api/backend/"))
        return route.fulfill({
          status: url.pathname.includes("/auth/") ? 401 : 200,
          contentType: "application/json",
          body: url.pathname.includes("/auth/") ? '{"detail":"No mock session"}' : "[]",
        });
      return route.continue();
    });
    const violations = [];
    page.on("console", (msg) => {
      if (/violates.*Content Security Policy|Refused to.*(script|style)/i.test(msg.text()))
        violations.push(msg.text());
    });
    const nonces = [];
    for (const path of ["/", "/login-admin", "/admin/dashboard", "/search", "/legal/privacy"]) {
      const response = await page.goto(base + path, { waitUntil: "networkidle" });
      assert.equal(response.status(), 200);
      const headers = response.headers();
      assert.equal(headers["x-frame-options"], "DENY");
      assert.equal(headers["x-content-type-options"], "nosniff");
      const nonce = headers["content-security-policy"].match(/nonce-([^']+)/)[1];
      nonces.push(nonce);
      // Check parser-inserted server scripts. Next may subsequently load trusted
      // dynamic chunks without nonce attributes under strict-dynamic.
      const html = await response.text();
      const scripts = html.match(/<script\b[^>]*>/g) ?? [];
      assert.ok(
        scripts.length > 0 && scripts.every((tag) => tag.includes(`nonce="${nonce}"`)),
        "Server-rendered scripts must carry the response nonce"
      );
      assert.ok((await page.locator("body").innerText()).length > 30);
      console.log("PASS page + headers + nonce " + path);
    }
    assert.equal(new Set(nonces).size, nonces.length);
    assert.deepEqual(violations, [], "Normal rendering must not violate CSP");
    await page.goto(base + "/login-admin", { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "Tampilkan kata sandi" }).click();
    assert.equal(
      await page
        .getByRole("button", { name: "Sembunyikan kata sandi" })
        .getAttribute("aria-pressed"),
      "true"
    );
    console.log("PASS hydrated password visibility toggle");
    // Inject into the HTTP document: DevTools evaluate has execution privileges
    // and cannot faithfully simulate a parser-inserted XSS payload.
    await page.route(base + "/login-admin", async (route) => {
      const original = await route.fetch();
      const body = (await original.text()).replace(
        "</body>",
        "<script>window.__cspInjected = true</script></body>"
      );
      await route.fulfill({ response: original, body });
    });
    await page.goto(base + "/login-admin", { waitUntil: "networkidle" });
    assert.equal(await page.evaluate(() => window.__cspInjected), undefined);
    console.log("PASS injected script blocked");
  } finally {
    if (browser) await browser.close();
    server.kill();
  }
})().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
