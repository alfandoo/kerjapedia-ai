const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

function harness(session, ok = true) {
  const calls = [];
  const auth = {
    getStoredSession: () => session,
    fetchWithAuthRetry: async (url, options) => {
      calls.push({ url, options });
      return { ok };
    },
  };
  let headers;
  function load(filename) {
    const exports = {};
    const source = fs.readFileSync(path.join(__dirname, "../src/features/chat/", filename), "utf8");
    const code = ts.transpileModule(source, {
      compilerOptions: { module: ts.ModuleKind.CommonJS },
    }).outputText;
    vm.runInNewContext(code, {
      exports,
      window: { localStorage: { getItem: () => "11111111-1111-4111-8111-111111111111" } },
      require(name) {
        if (name === "@/features/auth") return auth;
        if (name === "./request-headers") return headers;
        if (name.includes("api-client")) return { API_URL: "https://offline.invalid" };
        throw Error(name);
      },
    });
    return exports;
  }
  headers = load("request-headers.ts");
  return { api: load("feedback-api.ts"), calls };
}

test("feedback uses cookie session through auth retry", async () => {
  const h = harness({ access_token: "jwt" });
  await h.api.submitFeedback({ question: "Question", rating: "helpful", answer_id: "answer" });
  assert.equal(h.calls[0].options.headers.Authorization, undefined);
  assert.equal(h.calls[0].options.headers["X-KerjaPedia-Guest-ID"], undefined);
});
test("guest feedback leaves identity resolution to the BFF", async () => {
  const h = harness(null);
  await h.api.submitFeedback({ question: "Question", rating: "helpful" });
  assert.equal(h.calls[0].options.headers["X-KerjaPedia-Guest-ID"], undefined);
  assert.equal(h.calls[0].options.headers.Authorization, undefined);
});
test("rejected feedback is reported to the caller", async () => {
  const h = harness(null, false);
  await assert.rejects(
    h.api.submitFeedback({ question: "Question", rating: "helpful" }),
    /belum dapat disimpan/
  );
});
