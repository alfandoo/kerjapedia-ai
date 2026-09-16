const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const ts = require("typescript");
const path = require("node:path");

function harness(responses) {
  let session = { access_token: "old-jwt", refresh_token: "refresh", user: { id: "user" } };
  let cleared = false;
  const calls = [];
  const source = fs.readFileSync(path.join(__dirname, "../src/features/auth/api.ts"), "utf8");
  const code = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText;
  const exports = {};
  vm.runInNewContext(code, {
    exports,
    Headers,
    Event: class {},
    require(name) {
      if (name.includes("api-client")) return { API_URL: "https://offline.invalid" };
      if (name === "./session")
        return {
          getStoredSession: () => session,
          loadStoredSession: async () => {},
          setStoredSession: (next) => {
            session = next;
          },
          clearStoredSession: () => {
            cleared = true;
            session = null;
          },
          SESSION_STORAGE_KEY: "session",
        };
      throw Error("Unexpected module " + name);
    },
    window: {
      localStorage: {
        setItem: (_, value) => {
          session = JSON.parse(value);
        },
      },
      dispatchEvent() {},
    },
    fetch: async (url, options) => {
      calls.push({ url, options });
      const response = responses.shift();
      if (response instanceof Error) throw response;
      assert.ok(response, "Unexpected request");
      return response;
    },
  });
  return { signOut: exports.signOut, calls, cleared: () => cleared };
}
const response = (status, body = {}) => ({ status, ok: status === 200, json: async () => body });

test("successful logout revokes before local cleanup", async () => {
  const h = harness([response(200)]);
  await h.signOut();
  assert.equal(h.calls[0].options.headers.get("Authorization"), null);
  assert.equal(h.calls[0].options.headers.get("X-KerjaPedia-CSRF"), "1");
  assert.equal(h.cleared(), true);
});
for (const failure of [response(503), new Error("offline")]) {
  test("provider/network failure remains visible and retains session for retry", async () => {
    const h = harness([failure]);
    await assert.rejects(h.signOut(), /belum berhasil dicabut/);
    assert.equal(h.cleared(), false);
  });
}
test("expired cookie session refreshes server-side then retries logout", async () => {
  const h = harness([response(401), response(200, { user: { id: "user" } }), response(200)]);
  await h.signOut();
  assert.ok(h.calls[1].url.endsWith("/auth/refresh"));
  assert.equal(h.calls[2].options.headers.get("Authorization"), null);
  assert.equal(h.calls[1].options.body, undefined);
  assert.equal(h.cleared(), true);
});
