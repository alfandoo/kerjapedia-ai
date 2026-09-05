const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const ts = require("typescript");
const { NextRequest } = require("next/server");
const user = { user_id: "user", name: "User", email: "user@example.test", roles: ["admin"] };
function load(responses = [], production = true, maxBody = 50 * 1024 * 1024) {
  const exports = {};
  const calls = [];
  const source = fs.readFileSync(path.join(__dirname, "../src/app/api/backend/[...path]/route.ts"), "utf8").replace("const MAX_BODY = 50 * 1024 * 1024;", `const MAX_BODY = ${maxBody};`);
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, require, Buffer, Headers, URL, Response, ReadableStream, TransformStream, SyntaxError,
    process: { env: { NODE_ENV: production ? "production" : "development", API_INTERNAL_URL: "http://private-api.test:8000", APP_ORIGIN: "https://app.example.test" } },
    fetch: async (url, options) => {
      calls.push({ url: String(url), options });
      if (options.body instanceof ReadableStream) calls[calls.length - 1].body = await new Response(options.body).text();
      const result = responses.shift();
      assert.ok(result, "Unexpected upstream request");
      if (result instanceof Error) throw result;
      return result;
    },
  });
  return { calls, run: async (route, method = "POST", headers = {}, body) => {
    const req = new NextRequest("https://app.example.test/api/backend/" + route, { method,
      headers: { origin: "https://app.example.test", "x-kerjapedia-csrf": "1", ...headers },
      ...(body === undefined ? {} : { body: typeof body === "string" ? body : JSON.stringify(body) }),
    });
    return exports[method](req, { params: Promise.resolve({ path: route.split("/") }) });
  } };
}
const json = (data, status = 200) => Response.json(data, { status });
const tokens = () => json({ user: { ...user, refresh_token: "nested-secret" }, access_token: "access-secret", refresh_token: "refresh-secret", token_type: "bearer" });
const cookie = "__Host-kp-access=access-secret; __Host-kp-refresh=refresh-secret";

test("login returns only profile and sets host-only Secure HttpOnly cookies", async () => {
  const h = load([tokens()]);
  const result = await h.run("auth/login", "POST", {}, { email: user.email, password: "password", access_token: "forged" });
  assert.deepEqual(await result.json(), { user });
  const cookies = result.headers.getSetCookie();
  assert.equal(cookies.length, 2);
  for (const value of cookies) {
    for (const flag of ["HttpOnly", "Secure", "SameSite=lax", "Path=/"]) assert.ok(value.includes(flag));
    assert.ok(!value.includes("Domain="));
  }
  assert.equal(JSON.parse(h.calls[0].options.body).access_token, undefined);
  assert.equal(result.headers.get("cache-control"), "private, no-store");
});
test("refresh reads cookie and never accepts a token from browser JSON", async () => {
  const h = load([tokens()]);
  const result = await h.run("auth/refresh", "POST", { cookie }, { refresh_token: "forged" });
  assert.deepEqual(JSON.parse(h.calls[0].options.body), { refresh_token: "refresh-secret" });
  assert.deepEqual(await result.json(), { user });
});
test("backend receives only cookie bearer, not browser Authorization or Cookie", async () => {
  const h = load([json({ ok: true })]);
  await h.run("admin/stats", "GET", { cookie, authorization: "Bearer forged", "x-forwarded-for": "forged" });
  const headers = h.calls[0].options.headers;
  assert.equal(headers.get("authorization"), "Bearer access-secret");
  assert.equal(headers.get("cookie"), null);
  assert.equal(headers.get("x-forwarded-for"), null);
});
for (const headers of [{ origin: "https://evil.test" }, { origin: "null" }, { origin: "" }, { "x-kerjapedia-csrf": "" }, { "sec-fetch-site": "cross-site" }]) {
  test("CSRF rejected before backend call: " + JSON.stringify(headers), async () => {
    const h = load();
    const result = await h.run("auth/login", "POST", headers, { email: user.email, password: "password" });
    assert.equal(result.status, 403);
    assert.equal(h.calls.length, 0);
  });
}
test("successful logout revokes cookie token then expires both cookies", async () => {
  const h = load([json({ status: "ok" })]);
  const result = await h.run("auth/logout", "POST", { cookie });
  assert.equal(h.calls[0].options.headers.get("authorization"), "Bearer access-secret");
  assert.equal(result.headers.getSetCookie().filter(x => x.includes("Max-Age=0")).length, 2);
});
test("failed logout retains cookies and hides provider error details", async () => {
  const h = load([json({ detail: "provider-secret" }, 503)]);
  const result = await h.run("auth/logout", "POST", { cookie });
  assert.equal(result.status, 503);
  assert.equal(result.headers.getSetCookie().length, 0);
  assert.ok(!(await result.text()).includes("provider-secret"));
});
test("invalid refresh expires cookies but transient failure does not", async () => {
  for (const status of [401, 503]) {
    const h = load([json({}, status)]);
    const result = await h.run("auth/refresh", "POST", { cookie });
    assert.equal(result.headers.getSetCookie().length, status === 401 ? 2 : 0);
  }
});
test("guest requests retain guest identity and have no bearer", async () => {
  const h = load([json([])]);
  await h.run("chat/conversations", "GET", { cookie: "__Host-kp-guest=11111111-1111-4111-8111-111111111111", "x-kerjapedia-guest-id": "forged", authorization: "Bearer forged" });
  assert.equal(h.calls[0].options.headers.get("authorization"), null);
  assert.equal(h.calls[0].options.headers.get("x-kerjapedia-guest-id"), "11111111-1111-4111-8111-111111111111");
});
test("profile bootstrap only exposes approved fields", async () => {
  const h = load([json({ ...user, access_token: "leak" })]);
  const response = await h.run("auth/session", "GET", { cookie });
  assert.deepEqual(await response.json(), { user });
  assert.ok(h.calls[0].url.endsWith("/auth/me"));
});
test("path traversal, unknown auth routes and GET login are rejected", async () => {
  const h = load();
  for (const target of ["admin/../auth/login", "auth/unknown", "metrics"]) assert.equal((await h.run(target)).status, 404);
  assert.equal((await h.run("auth/login", "GET")).status, 405);
  assert.equal(h.calls.length, 0);
});
test("registration awaiting email confirmation never creates cookies", async () => {
  const h = load([json({ user, access_token: "", refresh_token: "" })]);
  const result = await h.run("auth/register", "POST", {}, { name: "User", email: user.email, password: "password" });
  assert.equal(result.status, 202);
  assert.equal(result.headers.getSetCookie().length, 0);
});
test("upstream redirects cannot forward credentials to another server", async () => {
  const h = load([new Response(null, { status: 307, headers: { location: "https://evil.test" } })]);
  assert.equal((await h.run("admin/stats", "GET", { cookie })).status, 502);
  assert.equal(h.calls[0].options.redirect, "manual");
});
test("login body is size bounded before backend access", async () => {
  const h = load();
  assert.equal((await h.run("auth/login", "POST", {}, "x".repeat(17000))).status, 413);
  assert.equal(h.calls.length, 0);
});
test("chat responses remain streaming and do not forward upstream cookies", async () => {
  const h = load([new Response("{event:delta}\n", { headers: { "content-type": "application/x-ndjson", "set-cookie": "unsafe=1" } })]);
  const response = await h.run("chat/ask-stream", "POST", { cookie }, { question: "Question" });
  assert.ok(response.body instanceof ReadableStream);
  assert.equal(response.headers.get("set-cookie"), null);
  assert.equal(await response.text(), "{event:delta}\n");
});

test("BFF stops oversized upload streams without trusting Content-Length", async () => {
  const h = load([], true, 16);
  const result = await h.run("admin/documents/upload", "POST", { cookie }, "%PDF-" + "x".repeat(12));
  assert.equal(result.status, 413);
});
test("BFF preserves PDF bytes below the upload limit", async () => {
  const h = load([json({ ok: true })], true, 16);
  const result = await h.run("admin/documents/upload", "POST", { cookie }, "%PDF-" + "x".repeat(11));
  assert.equal(result.status, 200);
  assert.equal(h.calls[0].body, "%PDF-" + "x".repeat(11));
});

test("guest identity is generated in an HttpOnly cookie, ignoring forged headers", async () => {
  const h = load([json([])]);
  const result = await h.run("chat/conversations", "GET", { "x-kerjapedia-guest-id": "forged" });
  const guest = h.calls[0].options.headers.get("x-kerjapedia-guest-id");
  assert.match(guest, /^[0-9a-f-]{36}$/);
  assert.notEqual(guest, "forged");
  const cookie = result.headers.get("set-cookie");
  for (const value of ["__Host-kp-guest=" + guest, "HttpOnly", "Secure", "SameSite=lax"]) assert.ok(cookie.includes(value));
});
