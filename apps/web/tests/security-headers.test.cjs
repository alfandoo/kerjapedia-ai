const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");
const { NextRequest } = require("next/server");
function load(mode) {
  const exports = {};
  const source = fs.readFileSync(path.join(__dirname, "../src/proxy.ts"), "utf8");
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, require, Buffer, Headers, URL, crypto: require("node:crypto").webcrypto,
    process: { env: { NODE_ENV: mode, NEXT_PUBLIC_API_URL: "https://api.example.test/v1" } },
  });
  return exports.proxy;
}
test("production CSP rejects inline script and eval and limits connections", () => {
  const response = load("production")(new NextRequest("https://app.example.test/"));
  const policy = response.headers.get("content-security-policy");
  const script = policy.split(";").map(x => x.trim()).find(x => x.startsWith("script-src "));
  assert.ok(!script.includes("unsafe-inline"));
  assert.ok(!script.includes("unsafe-eval"));
  assert.ok(policy.includes("connect-src 'self'"));
  for (const directive of ["frame-ancestors 'none'", "object-src 'none'", "base-uri 'none'", "script-src-attr 'none'"]) assert.ok(policy.includes(directive));
});
test("nonce changes per request and overrides forged request headers", () => {
  const proxy = load("production");
  const request = () => new NextRequest("https://app.example.test/", { headers: { "x-nonce": "forged", "content-security-policy": "default-src *" } });
  const first = proxy(request());
  const second = proxy(request());
  const nonce = first.headers.get("content-security-policy").match(/nonce-([^']+)/)[1];
  assert.notEqual(nonce, "forged");
  assert.notEqual(first.headers.get("content-security-policy"), second.headers.get("content-security-policy"));
  assert.equal(first.headers.get("x-middleware-request-x-nonce"), nonce);
  assert.equal(first.headers.get("cache-control"), "private, no-store");
});
test("development retains eval and websocket support for HMR", () => {
  const policy = load("development")(new NextRequest("http://localhost:3000/")).headers.get("content-security-policy");
  assert.ok(policy.includes("'unsafe-eval'"));
  assert.ok(policy.includes("ws: wss:"));
});
