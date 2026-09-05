const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const ts = require("typescript");
const user = { user_id: "owner", email: "owner@example.test", name: "Owner", roles: ["user"] };
function load(fetchResponse) {
  const exports = {}, removed = [];
  const storage = { removeItem: key => removed.push(key), setItem: () => { throw Error("Session must not write browser storage"); } };
  const source = fs.readFileSync(path.join(__dirname, "../src/features/auth/session.ts"), "utf8");
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
    exports, window: { localStorage: storage, sessionStorage: storage },
    require: name => name === "react" ? {} : { fetchWithAuthRetry: fetchResponse },
  });
  return { api: exports, removed };
}
test("session memory only contains profile and removes legacy credentials", () => {
  const h = load();
  h.api.setStoredSession({ access_token: "secret", refresh_token: "secret", user: { ...user, access_token: "nested" } });
  assert.equal(JSON.stringify(h.api.getStoredSession()), JSON.stringify({ user }));
  assert.equal(h.removed.length, 2);
  h.api.clearStoredSession();
  assert.equal(h.api.getStoredSession(), null);
});
test("late profile bootstrap cannot restore a locally cleared session", async () => {
  let resolveJson;
  const body = new Promise(resolve => { resolveJson = resolve; });
  const h = load(async () => ({ ok: true, json: () => body }));
  const pending = h.api.loadStoredSession();
  await new Promise(resolve => setImmediate(resolve));
  h.api.clearStoredSession();
  resolveJson({ user });
  await pending;
  assert.equal(h.api.getStoredSession(), null);
});
test("parallel bootstrap calls share one network request", async () => {
  let calls = 0;
  const h = load(async () => { calls++; return { ok: true, json: async () => ({ user }) }; });
  await Promise.all([h.api.loadStoredSession(), h.api.loadStoredSession()]);
  assert.equal(calls, 1);
  assert.equal(JSON.stringify(h.api.getStoredSession()), JSON.stringify({ user }));
});
