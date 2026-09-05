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
  await page.route("**/api/backend/auth/session", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({ user: { user_id: "user_e2e", email: "user@example.com", name: "Pengguna E2E", roles: ["user"] } }),
  }));
  await page.route("**/api/backend/auth/logout", route => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) }));
}

async function mockChat(
  page: Page,
  refusal = false,
  refusalReason = refusal ? "insufficient_retrieval_context" : null,
  refusalAnswer = "Saya tidak menemukan dasar yang cukup pada dokumen yang tersedia."
) {
  let hasConversation = false;
  const answer = {
    query: "Apakah pekerja PKWT memperoleh kompensasi?",
    answer: refusal
      ? refusalAnswer
      : "Pekerja PKWT berhak memperoleh uang kompensasi. Hak tersebut berlaku ketika hubungan kerja berakhir sesuai ketentuan yang berlaku. Besaran kompensasi dihitung berdasarkan masa kerja pekerja. Dasar dan rincian hukumnya dapat diperiksa melalui sumber resmi yang disertakan pada jawaban ini.",
    citations: refusal ? [] : [citation],
    confidence: refusal ? 0 : 0.95,
    related_documents: [],
    refusal_reason: refusalReason,
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
  test.setTimeout(45_000);
  const runtimeErrors = monitorRuntimeErrors(page);
  await page.setViewportSize({ width: 1584, height: 960 });
  await useAuthenticatedSession(page);
  await mockChat(page);
  await page.goto("/");

  await expect(page).toHaveTitle("KerjaPedia AI");
  await expect(
    page.getByText(/Build Error|Runtime Error|Application error|Unhandled Runtime Error/i)
  ).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Apa yang ingin Anda pahami?" })).toBeVisible();
  await expect(page.locator(".authenticated-shell")).toBeVisible();
  await page.getByLabel("Ketik pertanyaan Anda").fill("Apakah pekerja PKWT memperoleh kompensasi?");
  await page.getByLabel("Ketik pertanyaan Anda").press("Enter");

  await expect(
    page.getByRole("main").getByText("Pekerja PKWT berhak memperoleh uang kompensasi.")
  ).toBeVisible();
  await expect(page.locator(".editorial-answer-content > p")).toHaveCount(2);
  await expect(page.getByRole("button", { name: "Edit pesan" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Salin pesan" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Salin jawaban" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Bagikan jawaban" })).toBeVisible();
  await page.getByRole("button", { name: "Edit pesan" }).click();
  await expect(page.getByLabel("Ketik pertanyaan Anda")).toHaveValue(
    "Apakah pekerja PKWT memperoleh kompensasi?"
  );
  await expect(page.getByLabel("Ketik pertanyaan Anda")).toBeFocused();
  await expect(page.getByText("Peraturan Pemerintah Nomor 35 Tahun 2021")).toHaveCount(0);
  await page.getByRole("button", { name: "Lihat 1 sumber resmi" }).click();
  await expect(page.getByText("Peraturan Pemerintah Nomor 35 Tahun 2021")).toBeVisible();
  await expect(page.getByRole("link", { name: /Buka PDF dokumen/ })).toBeVisible();
  await expect(page.getByText(/Pasal 15/)).toBeVisible();
  await page.getByRole("tab", { name: "Pasal" }).click();
  await expect(page.getByRole("tabpanel")).toContainText("Perjanjian Kerja Waktu Tertentu");
  await expect(page.getByRole("tabpanel")).not.toContainText(citation.quote);
  await expect(page.getByRole("link", { name: /Buka PDF dokumen/ })).toHaveAttribute(
    "href",
    /\/documents\/PP-35-2021\/pdf#page=12$/
  );
  await page.getByRole("tab", { name: "Kutipan" }).click();
  await expect(page.getByRole("tabpanel")).toContainText(citation.quote);
  await expect(page.getByRole("tabpanel")).not.toContainText("Status");
  await expect(page.getByRole("link", { name: /Buka PDF dokumen/ })).toHaveAttribute(
    "href",
    /\/documents\/PP-35-2021\/pdf#page=12$/
  );
  await page.getByRole("tab", { name: "Sumber" }).click();
  await page.getByRole("tab", { name: "Pasal" }).hover();
  await expect(page.getByRole("tab", { name: "Pasal" })).toHaveCSS(
    "background-color",
    "rgba(0, 0, 0, 0)"
  );
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

  await page.getByRole("button", { name: "Chat baru" }).first().click();
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

test("desktop sidebar collapses and persists", async ({ page }, testInfo) => {
  await mockEmptyHistory(page);
  await page.goto("/");

  const toggle = page.getByRole("button", { name: "Tutup sidebar" });
  await expect(toggle).toBeVisible();
  await expect(page.getByRole("link", { name: "KerjaPedia AI beranda" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Cari chat" }).first()).toBeVisible();
  const sidebarScreenshot = join(tmpdir(), "kerjapedia-sidebar-header.png");
  await page.screenshot({ path: sidebarScreenshot });
  await testInfo.attach("sidebar-header", {
    path: sidebarScreenshot,
    contentType: "image/png",
  });
  await toggle.click();
  await expect(page.getByRole("button", { name: "Buka sidebar" })).toBeVisible();
  await expect(page.locator(".desktop-sidebar")).toBeVisible();
  await expect(page.locator(".desktop-sidebar")).toHaveCSS("width", "64px");
  await expect(page.locator(".desktop-sidebar").getByText("Chat baru")).toBeHidden();
  await expect(
    page.locator(".collapsed-sidebar-rail").getByRole("link", { name: "KerjaPedia AI beranda" })
  ).toBeVisible();
  await expect(
    page.locator(".collapsed-sidebar-rail").getByRole("button", { name: "Percakapan baru" })
  ).toBeVisible();
  await expect(
    page.locator(".collapsed-sidebar-rail").getByRole("button", { name: "Cari chat" })
  ).toBeVisible();
  await expect(
    page.locator(".collapsed-sidebar-rail").getByRole("button", { name: "Masuk atau daftar" })
  ).toBeVisible();
  const collapsedSidebarScreenshot = join(tmpdir(), "kerjapedia-sidebar-collapsed.png");
  await page.screenshot({ path: collapsedSidebarScreenshot });
  await testInfo.attach("sidebar-collapsed", {
    path: collapsedSidebarScreenshot,
    contentType: "image/png",
  });
  await page.reload();
  await expect(page.getByRole("button", { name: "Buka sidebar" })).toBeVisible();
  await expect(page.locator(".desktop-sidebar")).toHaveCSS("width", "64px");
});

test("sidebar search filters saved chats", async ({ page }) => {
  await useAuthenticatedSession(page);
  await page.route("**/chat/conversations", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          conversation_id: "conv_pkwt",
          title: "Kompensasi PKWT",
          created_at: "2026-07-24T10:00:00Z",
          updated_at: "2026-07-24T10:01:00Z",
          message_count: 2,
        },
        {
          conversation_id: "conv_thr",
          title: "Batas pembayaran THR",
          created_at: "2026-07-24T11:00:00Z",
          updated_at: "2026-07-24T11:01:00Z",
          message_count: 2,
        },
      ]),
    });
  });
  await page.goto("/");

  await page.getByRole("button", { name: "Cari chat" }).first().click();
  const search = page.getByRole("searchbox", { name: "Cari chat" });
  await expect(search).toBeFocused();
  await search.fill("THR");
  await expect(page.getByText("Batas pembayaran THR")).toBeVisible();
  await expect(page.getByText("Kompensasi PKWT")).toBeHidden();
});

test("authenticated user logs out from the profile area", async ({ page }, testInfo) => {
  await useAuthenticatedSession(page);
  await mockEmptyHistory(page);
  await page.goto("/");

  const profileTrigger = page.getByRole("button", { name: "Buka menu profil Pengguna E2E" });
  await expect(profileTrigger).toBeVisible();
  await profileTrigger.click();
  const profileMenu = page.getByRole("menu", { name: "Menu profil pengguna" });
  await expect(profileMenu).toBeVisible();
  await expect(profileMenu.getByRole("menuitem", { name: "Profil & riwayat" })).toBeFocused();
  const profileMenuScreenshot = join(tmpdir(), "kerjapedia-profile-menu.png");
  await page.screenshot({ path: profileMenuScreenshot });
  await testInfo.attach("profile-menu", {
    path: profileMenuScreenshot,
    contentType: "image/png",
  });
  await profileMenu.getByRole("menuitem", { name: "Keluar" }).click();

  await expect(page.getByText("Simpan percakapan Anda")).toBeVisible();
  await expect(page.getByRole("button", { name: "Daftar gratis" })).toBeVisible();
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem("kerjapedia-session-v1")))
    .toBeNull();
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
  await expect(page.getByRole("button", { name: "Masuk" })).toHaveCount(2);
  await expect(page.getByRole("button", { name: "Daftar gratis" })).toBeVisible();
  await expect(page.getByText("Apa yang ingin Anda pahami?")).toBeVisible();
  await expect(page.locator(".editorial-suggestions")).toBeHidden();
});

test("guest authenticates through the two-step modal", async ({ page }, testInfo) => {
  let registrationPayload: Record<string, string> | null = null;
  await page.route("**/auth/register", async (route) => {
    registrationPayload = route.request().postDataJSON() as Record<string, string>;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        user: {
          user_id: "user_modal",
          email: "user@example.com",
          name: "Pengguna Modal",
          roles: ["user"],
        },
      }),
    });
  });
  await mockEmptyHistory(page);
  await page.goto("/");

  const trigger = page.getByRole("button", { name: "Daftar gratis" });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "Buat akun KerjaPedia" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel("Nama lengkap")).toBeVisible();
  await expect(dialog.getByRole("button", { name: /Lanjutkan dengan Google/ })).toBeDisabled();
  const desktopModalScreenshot = join(tmpdir(), "kerjapedia-auth-modal-desktop.png");
  await page.screenshot({ path: desktopModalScreenshot });
  await testInfo.attach("auth-modal-desktop", {
    path: desktopModalScreenshot,
    contentType: "image/png",
  });

  await dialog.getByLabel("Nama lengkap").fill("Pengguna Modal");
  await dialog.getByLabel("Alamat email").fill("user@example.com");
  await dialog.getByRole("button", { name: "Lanjutkan", exact: true }).click();
  const passwordInput = dialog.getByRole("textbox", { name: "Password" });
  await expect(passwordInput).toBeFocused();
  await passwordInput.fill("secret-aman");
  await expect(passwordInput).toHaveAttribute("type", "password");
  await dialog.getByRole("button", { name: "Tampilkan password" }).click();
  await expect(passwordInput).toHaveAttribute("type", "text");
  const passwordModalScreenshot = join(tmpdir(), "kerjapedia-auth-modal-password.png");
  await page.screenshot({ path: passwordModalScreenshot });
  await testInfo.attach("auth-modal-password", {
    path: passwordModalScreenshot,
    contentType: "image/png",
  });
  await dialog.getByRole("button", { name: "Sembunyikan password" }).click();
  await expect(passwordInput).toHaveAttribute("type", "password");
  await dialog.getByRole("button", { name: "Buat akun" }).click();

  await expect(dialog).toBeHidden();
  expect(registrationPayload).toEqual({
    name: "Pengguna Modal",
    email: "user@example.com",
    password: "secret-aman",
  });
  await expect(page.getByRole("button", { name: "Buka menu profil Pengguna Modal" })).toBeVisible();
  await expect(page.getByText("Pengguna Modal")).toHaveCount(1);
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem("kerjapedia-session-v1")))
    .toBeNull();
});

test("auth modal fits a mobile viewport", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Masuk" }).last().click();

  const dialog = page.getByRole("dialog", { name: "Masuk ke KerjaPedia" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toBeInViewport();
  await expect(dialog.getByRole("button", { name: "Lanjutkan", exact: true })).toBeInViewport();
  const mobileModalScreenshot = join(tmpdir(), "kerjapedia-auth-modal-mobile.png");
  await page.screenshot({ path: mobileModalScreenshot });
  await testInfo.attach("auth-modal-mobile", {
    path: mobileModalScreenshot,
    contentType: "image/png",
  });
});

test("auth modal closes with Escape and restores trigger focus", async ({ page }) => {
  await page.goto("/");
  const trigger = page.getByRole("button", { name: "Masuk" }).last();
  await trigger.click();
  await expect(page.getByRole("dialog", { name: "Masuk ke KerjaPedia" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Masuk ke KerjaPedia" })).toBeHidden();
  await expect(trigger).toBeFocused();

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

test("user sees the employment scope boundary", async ({ page }) => {
  const refusal =
    "Maaf, saya tidak tahu untuk pertanyaan tersebut. KerjaPedia AI difokuskan khusus pada regulasi dan persoalan ketenagakerjaan Indonesia.";
  await mockChat(page, true, "out_of_scope_query", refusal);
  await page.goto("/");

  await page.getByLabel("Ketik pertanyaan Anda").fill("Siapa presiden Prancis?");
  await page.getByRole("button", { name: "Kirim" }).click();

  await expect(page.getByText(refusal)).toBeVisible();
  await expect(
    page.getByText("KerjaPedia AI hanya menjawab topik ketenagakerjaan Indonesia.")
  ).toBeVisible();
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
