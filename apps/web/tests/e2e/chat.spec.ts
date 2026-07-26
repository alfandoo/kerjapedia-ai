import { expect, test, type Page } from "@playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";

const citation = {
  citation_id: "cit_001",
  chunk_id: "PP-35-2021-v1-pasal-15",
  document_id: "PP-35-2021",
  document_title: "Peraturan Pemerintah Nomor 35 Tahun 2021",
  short_title: "PP 35/2021",
  legal_status: "active",
  chapter: "BAB II",
  section: "Perjanjian Kerja Waktu Tertentu",
  article: "Pasal 15",
  paragraph: "Ayat (1)",
  page_start: 12,
  page_end: 12,
  quote: "Pekerja PKWT berhak memperoleh uang kompensasi.",
  source_url: "https://peraturan.bpk.go.id/",
  local_file: "dataset/PP-35-2021.pdf",
  retrieval_score: 0.95,
  rerank_score: 0.93,
};

async function useAuthenticatedSession(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "kerjapedia-session-v1",
      JSON.stringify({
        access_token: "e2e-token",
        user: {
          user_id: "user_e2e",
          email: "user@example.com",
          name: "Pengguna E2E",
          roles: ["user"],
        },
      })
    );
  });
}

async function mockChat(page: Page, refusal = false) {
  let hasConversation = false;
  const answer = {
    query: "Apakah pekerja PKWT memperoleh kompensasi?",
    answer: refusal
      ? "Saya tidak menemukan dasar yang cukup pada dokumen yang tersedia."
      : "Pekerja PKWT berhak memperoleh uang kompensasi.",
    citations: refusal ? [] : [citation],
    confidence: refusal ? 0 : 0.95,
    related_documents: [],
    refusal_reason: refusal ? "insufficient_retrieval_context" : null,
    clarification_question: null,
    disclaimer: "Informasi ini bukan pengganti nasihat hukum profesional.",
    prompt_version_id: "kerjapedia-grounded-answer-v2",
    retrieved_chunk_ids: refusal ? [] : [citation.chunk_id],
    warnings: [],
  };

  await page.route("**/chat/conversations", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        hasConversation
          ? [
              {
                conversation_id: "conv_e2e",
                title: answer.query,
                created_at: "2026-07-24T10:00:00Z",
                updated_at: "2026-07-24T10:01:00Z",
                message_count: 2,
              },
            ]
          : []
      ),
    });
  });
  await page.route("**/chat/conversations/conv_e2e", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        conversation_id: "conv_e2e",
        title: answer.query,
        created_at: "2026-07-24T10:00:00Z",
        updated_at: "2026-07-24T10:01:00Z",
        messages: [
          {
            role: "user",
            content: answer.query,
            created_at: "2026-07-24T10:00:00Z",
            metadata: {},
          },
          {
            role: "assistant",
            content: answer.answer,
            created_at: "2026-07-24T10:01:00Z",
            metadata: { answer },
          },
        ],
      }),
    });
  });
  await page.route("**/chat/ask/stream", async (route) => {
    hasConversation = true;
    const response = {
      conversation_id: "conv_e2e",
      answer,
      latency_ms: 42,
      retrieval_score: refusal ? null : 0.95,
      token_usage: { prompt_tokens: 0, completion_tokens: 0 },
    };
    await route.fulfill({
      status: 200,
      contentType: "application/x-ndjson",
      body: [
        JSON.stringify({
          event: "start",
          conversation_id: "conv_e2e",
          status: "Menganalisis pertanyaan",
        }),
        JSON.stringify({ event: "thinking", status: "Menelusuri regulasi resmi" }),
        JSON.stringify({ event: "delta", content: answer.answer }),
        JSON.stringify({ event: "done", response }),
        "",
      ].join("\n"),
    });
  });
  await page.route("**/feedback", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
}

function monitorRuntimeErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}

async function mockEmptyHistory(page: Page) {
  await page.route("**/chat/conversations", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });
}

test("user receives a sourced answer", async ({ page }, testInfo) => {
  const runtimeErrors = monitorRuntimeErrors(page);
  await page.setViewportSize({ width: 1584, height: 960 });
  await useAuthenticatedSession(page);
  await mockChat(page);
  await page.goto("/");

  await expect(page).toHaveTitle("KerjaPedia AI");
  await expect(
    page.getByText(/Build Error|Runtime Error|Application error|Unhandled Runtime Error/i)
  ).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Asisten Regulasi Ketenagakerjaan" })
  ).toBeVisible();
  await page.getByLabel("Ketik pertanyaan Anda").fill("Apakah pekerja PKWT memperoleh kompensasi?");
  await page.getByRole("button", { name: "Kirim" }).click();

  await expect(
    page.getByRole("main").getByText("Pekerja PKWT berhak memperoleh uang kompensasi.")
  ).toBeVisible();
  await expect(page.getByText("Peraturan Pemerintah Nomor 35 Tahun 2021")).toHaveCount(0);
  await page.getByRole("button", { name: "Lihat 1 sumber resmi" }).click();
  await expect(page.getByText("Peraturan Pemerintah Nomor 35 Tahun 2021")).toBeVisible();
  await expect(page.getByRole("link", { name: /Buka sumber resmi/ })).toBeVisible();
  await expect(page.getByText(/Pasal 15/)).toBeVisible();
  const desktopSourceScreenshot = join(tmpdir(), "kerjapedia-chatgpt-desktop-source.png");
  await page.screenshot({ path: desktopSourceScreenshot });
  await page.setViewportSize({ width: 1280, height: 768 });
  const laptopSourceScreenshot = join(tmpdir(), "kerjapedia-chatgpt-laptop-source.png");
  await page.screenshot({ path: laptopSourceScreenshot });
  const history = page.getByLabel("Riwayat percakapan");
  const savedConversation = history
    .locator(".editorial-history-item")
    .filter({ hasText: "Apakah pekerja PKWT" });
  await expect(savedConversation).toBeVisible();

  await history.getByRole("button", { name: /Percakapan baru/ }).click();
  await expect(page.getByRole("heading", { name: "Apa yang ingin Anda pahami?" })).toBeVisible();
  await savedConversation.click();
  await expect(
    page.getByRole("main").getByText("Pekerja PKWT berhak memperoleh uang kompensasi.")
  ).toBeVisible();
  expect(runtimeErrors).toEqual([]);
  const desktopScreenshot = join(tmpdir(), "kerjapedia-chat-desktop.png");
  await page.screenshot({ path: desktopScreenshot });
  await testInfo.attach("sourced-answer", {
    path: desktopScreenshot,
    contentType: "image/png",
  });
});

test("desktop sidebar collapses and persists", async ({ page }) => {
  await mockEmptyHistory(page);
  await page.goto("/");

  const toggle = page.getByRole("button", { name: "Tutup sidebar" });
  await expect(toggle).toBeVisible();
  await toggle.click();
  await expect(page.getByRole("button", { name: "Buka sidebar" })).toBeVisible();
  await expect(page.locator(".desktop-sidebar")).toBeHidden();
  await page.reload();
  await expect(page.getByRole("button", { name: "Buka sidebar" })).toBeVisible();
});

test("guest conversation history is not shown or persisted in the sidebar", async ({ page }) => {
  await page.route("**/chat/conversations", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          conversation_id: "conv_hidden_guest",
          title: "Percakapan guest lama",
          created_at: "2026-07-24T10:00:00Z",
          updated_at: "2026-07-24T10:01:00Z",
          message_count: 2,
        },
      ]),
    });
  });
  await page.goto("/");

  await expect(page.getByText("Simpan percakapan Anda")).toBeVisible();
  await expect(page.getByText("Percakapan guest lama")).toBeHidden();
  await expect(page.getByRole("link", { name: "Masuk" })).toHaveCount(2);
  await expect(page.getByRole("link", { name: "Daftar gratis" })).toBeVisible();
  await expect(page.getByText("Apa yang ingin Anda pahami?")).toBeVisible();
  await expect(page.locator(".editorial-suggestions")).toBeHidden();
  await expect(page.getByRole("link", { name: "Daftar gratis" })).toHaveAttribute(
    "href",
    "/login?mode=signup"
  );
  await page.goto("/login?mode=signup");
  await expect(page.getByRole("heading", { name: "Daftar gratis" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Buat akun" })).toBeVisible();
});

test("user renames and deletes a conversation from history", async ({ page }, testInfo) => {
  await useAuthenticatedSession(page);
  let title = "Hak kompensasi pekerja PKWT";
  let exists = true;
  await page.route("**/chat/conversations", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        exists
          ? [
              {
                conversation_id: "conv_actions",
                title,
                created_at: "2026-07-24T10:00:00Z",
                updated_at: "2026-07-24T10:01:00Z",
                message_count: 2,
              },
            ]
          : []
      ),
    });
  });
  await page.route("**/chat/conversations/conv_actions", async (route) => {
    if (route.request().method() === "PATCH") {
      title = (route.request().postDataJSON() as { title: string }).title;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          conversation_id: "conv_actions",
          title,
          created_at: "2026-07-24T10:00:00Z",
          updated_at: "2026-07-24T10:02:00Z",
          message_count: 2,
        }),
      });
      return;
    }
    if (route.request().method() === "DELETE") {
      exists = false;
      await route.fulfill({ status: 204 });
      return;
    }
    await route.fulfill({ status: 404, body: "{}" });
  });
  await page.goto("/");

  await page.getByRole("button", { name: /Tindakan untuk Hak kompensasi/ }).click();
  await page.getByRole("menuitem", { name: "Ubah judul" }).click();
  await page.getByLabel("Ubah judul").fill("Kompensasi PKWT");
  await page.getByRole("button", { name: "Simpan" }).click();
  await expect(page.getByText("Kompensasi PKWT")).toBeVisible();

  await page.getByRole("button", { name: "Tindakan untuk Kompensasi PKWT" }).click();
  await page.screenshot({ path: join(tmpdir(), "kerjapedia-chat-history-actions.png") });
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("menuitem", { name: "Hapus chat" }).click();
  await expect(
    page.getByText("Belum ada percakapan. Ajukan pertanyaan pertama Anda.")
  ).toBeVisible();

  await testInfo.attach("history-actions", {
    path: join(tmpdir(), "kerjapedia-chat-history-actions.png"),
    contentType: "image/png",
  });
});

test("user sees a refusal when context is insufficient", async ({ page }, testInfo) => {
  const runtimeErrors = monitorRuntimeErrors(page);
  await mockChat(page, true);
  await page.goto("/");

  await expect(page).toHaveTitle("KerjaPedia AI");
  await expect(
    page.getByText(/Build Error|Runtime Error|Application error|Unhandled Runtime Error/i)
  ).toHaveCount(0);
  await page.getByLabel("Ketik pertanyaan Anda").fill("Berapa harga saham perusahaan hari ini?");
  await page.getByRole("button", { name: "Kirim" }).click();

  await expect(
    page.getByText("Saya tidak menemukan dasar yang cukup pada dokumen yang tersedia.")
  ).toBeVisible();
  await expect(
    page.getByText("Dasar dokumen belum cukup untuk menjawab pertanyaan ini dengan aman.")
  ).toBeVisible();
  expect(runtimeErrors).toEqual([]);
  await testInfo.attach("refusal", {
    body: await page.screenshot(),
    contentType: "image/png",
  });
});

test("mobile user opens and closes the source bottom sheet", async ({ page }, testInfo) => {
  const runtimeErrors = monitorRuntimeErrors(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await mockChat(page);
  await page.goto("/");

  await page.getByLabel("Ketik pertanyaan Anda").fill("Apakah pekerja PKWT memperoleh kompensasi?");
  await page.getByRole("button", { name: "Kirim" }).click();
  await page.getByRole("button", { name: "Lihat 1 sumber resmi" }).click();

  const dialog = page.getByRole("dialog", { name: "Sumber dan kutipan" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Peraturan Pemerintah Nomor 35 Tahun 2021")).toBeVisible();
  await expect(page.getByRole("button", { name: "Tutup sumber dan kutipan" })).toBeFocused();
  const mobileScreenshot = join(tmpdir(), "kerjapedia-chat-mobile-sources.png");
  await page.screenshot({ path: mobileScreenshot });
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  expect(runtimeErrors).toEqual([]);
  await testInfo.attach("mobile-sources", {
    path: mobileScreenshot,
    contentType: "image/png",
  });
});

test("mobile guest opens the navigation drawer", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockEmptyHistory(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Buka menu" }).click();
  const menuDialog = page.getByRole("dialog", { name: "Menu KerjaPedia" });
  await expect(menuDialog).toBeVisible();
  await expect(page.getByRole("button", { name: "Tutup menu" }).last()).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(menuDialog).toBeHidden();
  await expect(page.getByRole("button", { name: "Buka menu" })).toBeFocused();
});

test("user can cancel an in-flight request", async ({ page }, testInfo) => {
  await mockEmptyHistory(page);
  await page.route("**/chat/ask/stream", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 2_000));
    await route.fulfill({ status: 503, contentType: "application/json", body: "{}" });
  });
  await page.goto("/");

  await page.getByLabel("Ketik pertanyaan Anda").fill("Tolong cari aturan THR");
  await page.getByRole("button", { name: "Kirim" }).click();
  await expect(page.getByText("Menganalisis pertanyaan")).toBeVisible();
  const thinkingScreenshot = join(tmpdir(), "kerjapedia-chat-thinking.png");
  await page.screenshot({ path: thinkingScreenshot });
  await page.getByRole("button", { name: "Batalkan" }).click();

  await expect(
    page.getByText("Respons dihentikan. Anda dapat melanjutkan dengan pertanyaan baru.")
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Kirim" })).toBeVisible();
  await testInfo.attach("thinking-state", {
    path: thinkingScreenshot,
    contentType: "image/png",
  });
});

test("user sees a useful API error", async ({ page }) => {
  await mockEmptyHistory(page);
  await page.route("**/chat/ask/stream", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Layanan jawaban sedang tidak tersedia." }),
    });
  });
  await page.goto("/");

  await page.getByLabel("Ketik pertanyaan Anda").fill("Apa aturan waktu kerja?");
  await page.getByRole("button", { name: "Kirim" }).click();

  await expect(
    page.getByRole("alert").filter({ hasText: "Layanan jawaban sedang tidak tersedia." })
  ).toBeVisible();
});
