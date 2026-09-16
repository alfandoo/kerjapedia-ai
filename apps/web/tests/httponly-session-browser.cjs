const { chromium } = require("playwright");
const { spawn } = require("node:child_process");
const http = require("node:http");
const assert = require("node:assert/strict");
const base = "http://127.0.0.1:3101";
const user = {
  user_id: "mock-admin",
  email: "admin@example.test",
  name: "Admin Cookie Test",
  roles: ["admin"],
};
(async () => {
  let access = "mock-access-1",
    refresh = "mock-refresh-1",
    revoked = false,
    refreshCount = 0;
  const calls = [];
  const fakeApi = http.createServer(async (req, res) => {
    let body = "";
    for await (const chunk of req) body += chunk;
    calls.push({
      path: req.url,
      authorization: req.headers.authorization,
      cookie: req.headers.cookie,
    });
    const reply = (status, data) => {
      res.writeHead(status, { "content-type": "application/json" });
      res.end(JSON.stringify(data));
    };
    if (req.url === "/auth/login") {
      revoked = false;
      return reply(200, { user, access_token: access, refresh_token: refresh });
    }
    if (req.url === "/auth/refresh") {
      if (revoked || JSON.parse(body).refresh_token !== refresh) return reply(401, {});
      refreshCount++;
      access = "mock-access-" + (refreshCount + 1);
      refresh = "mock-refresh-" + (refreshCount + 1);
      return reply(200, { user, access_token: access, refresh_token: refresh });
    }
    if (req.url === "/auth/me")
      return reply(!revoked && req.headers.authorization === "Bearer " + access ? 200 : 401, user);
    if (req.url === "/auth/logout") {
      revoked = true;
      return reply(200, { status: "ok" });
    }
    if (req.url.startsWith("/admin"))
      return reply(503, { detail: "Mock admin dataset unavailable" });
    if (req.url === "/chat/ask/stream") {
      res.writeHead(200, { "content-type": "application/x-ndjson" });
      res.write('{"event":"delta","content":"hello"}\n');
      return setTimeout(() => res.end('{"event":"done"}\n'), 20);
    }
    if (req.url === "/feedback") return reply(200, { feedback_id: "mock-feedback" });
    return reply(200, []);
  });
  await new Promise((resolve, reject) => {
    fakeApi.once("error", reject);
    fakeApi.listen(3102, "127.0.0.1", resolve);
  });
  const server = spawn(
    process.execPath,
    ["node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "3101"],
    {
      env: {
        ...process.env,
        NEXT_DIST_DIR: ".next-security-headers",
        API_INTERNAL_URL: "http://127.0.0.1:3102",
        APP_ORIGIN: base,
      },
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    }
  );
  let output = "";
  server.stdout.on("data", (x) => (output += x));
  server.stderr.on("data", (x) => (output += x));
  let browser;
  try {
    let ready = false;
    for (let i = 0; i < 80; i++) {
      if (server.exitCode !== null) throw Error(output.slice(-1000));
      try {
        ready = (await fetch(base + "/login-admin")).ok;
      } catch {}
      if (ready) break;
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    assert.ok(ready);
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    await context.addInitScript(() => {
      for (const key of ["localStorage", "sessionStorage"])
        Object.defineProperty(window, key, {
          get() {
            throw Error("Web Storage forbidden");
          },
        });
    });
    const page = await context.newPage();
    page.setDefaultTimeout(20000);
    page.setDefaultNavigationTimeout(60000);
    page.on("pageerror", (error) => console.log("BROWSER ERROR " + error.message));
    await page.route("**/*", (route) =>
      new URL(route.request().url()).origin === base ? route.continue() : route.abort()
    );
    await page.goto(base + "/login-admin");
    await page.getByRole("button", { name: "Tampilkan kata sandi" }).click();
    await page.getByRole("button", { name: "Sembunyikan kata sandi" }).click();
    await page.getByLabel("Email", { exact: true }).fill(user.email);
    await page.locator('input[type="password"]').fill("mock-password");
    const [loginResponse] = await Promise.all([
      page.waitForResponse((r) => r.url().endsWith("/api/backend/auth/login")),
      page.locator('form button[type="submit"]').click(),
    ]);
    assert.deepEqual(await loginResponse.json(), { user });
    await page.waitForURL("**/admin/dashboard");
    const cookies = (await context.cookies()).filter((c) => /kp-(access|refresh)$/.test(c.name));
    assert.equal(cookies.length, 2);
    assert.ok(cookies.every((c) => c.httpOnly && c.secure && c.sameSite === "Lax"));
    const visible = await page.evaluate(() => document.cookie);
    assert.ok(!/mock-access|mock-refresh/.test(visible));
    console.log(
      "PASS real login form, HttpOnly cookies, no browser-storage tokens with Web Storage blocked"
    );
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.getByText(user.name, { exact: true }).first().waitFor({ state: "visible" });
    console.log("PASS session/profile restored after reload");
    // Invalidate access only. Bootstrap must refresh cookie without exposing tokens.
    access = "expired-marker";
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.getByText(user.name, { exact: true }).first().waitFor({ state: "visible" });
    assert.ok(refreshCount > 0);
    console.log("PASS automatic server-cookie refresh after access expiry");
    const stream = await page.evaluate(async () => {
      const response = await fetch("/api/backend/chat/ask/stream", {
        method: "POST",
        headers: { "X-KerjaPedia-CSRF": "1", "Content-Type": "application/json" },
        body: JSON.stringify({ question: "mock" }),
      });
      return { status: response.status, body: await response.text() };
    });
    assert.equal(stream.status, 200);
    assert.ok(stream.body.includes("hello"));
    const missingCsrf = await page.evaluate(
      async () => (await fetch("/api/backend/feedback", { method: "POST", body: "{}" })).status
    );
    assert.equal(missingCsrf, 403);
    const forgedOrigin = await fetch(base + "/api/backend/auth/logout", {
      method: "POST",
      headers: { Origin: "https://evil.test", "X-KerjaPedia-CSRF": "1" },
    });
    assert.equal(forgedOrigin.status, 403);
    assert.equal(revoked, false);
    console.log("PASS streaming chat and CSRF rejection");
    // Verify the shared logout flow via the actual admin menu.
    await page.getByText(user.name, { exact: true }).first().click();
    await page.getByRole("menuitem", { name: "Logout", exact: true }).click();
    await page.waitForURL("**/login-admin");
    assert.equal(revoked, true);
    assert.equal(
      (await context.cookies()).filter((c) => /kp-(access|refresh)$/.test(c.name)).length,
      0
    );
    assert.ok(
      calls
        .filter((c) => c.path === "/auth/logout")
        .every((c) => c.authorization?.startsWith("Bearer mock-access-"))
    );
    assert.ok(calls.every((c) => !c.cookie));
    console.log("PASS logout UI revokes backend and deletes cookies");
    if (process.env.RUN_EXISTING_E2E === "1") {
      await browser.close();
      browser = null;
      const code = await new Promise((resolve, reject) => {
        const runner = spawn(
          process.execPath,
          [
            "node_modules/@playwright/test/cli.js",
            "test",
            "--workers=2",
            "--timeout=20000",
            "--max-failures=3",
          ],
          {
            env: { ...process.env, PLAYWRIGHT_BASE_URL: base },
            windowsHide: true,
            stdio: "inherit",
          }
        );
        runner.once("error", reject);
        runner.once("exit", resolve);
      });
      assert.equal(code, 0, "Existing Playwright regressions failed");
    }
  } catch (error) {
    console.log(
      "UPSTREAM PATHS",
      calls.map((c) => c.path)
    );
    console.log("SERVER", output.slice(-1800));
    throw error;
  } finally {
    if (browser) await browser.close();
    server.kill();
    fakeApi.closeAllConnections();
    await new Promise((resolve) => fakeApi.close(resolve));
  }
})().catch((error) => {
  console.error(error.stack);
  process.exitCode = 1;
});
