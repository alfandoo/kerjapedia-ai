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
  await page.route("**/api/backend/auth/session", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        user: {
          user_id: "user_e2e",
          email: "user@example.com",
          name: "Pengguna E2E",
          roles: ["user"],
        },
      }),
    })
  );
  await page.route("**/api/backend/auth/logout", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok" }),
    })
  );
}

async function mockChat(
  page: Page,
  refusal = false,
  refusalReason = refusal ? "insufficient_retrieval_context" : null,
  refusalAnswer = "Saya tidak menemukan dasar yang cukup pada dokumen yang tersedia.",
  onRequest?: (payload: Record<string, unknown>) => void
) {
  let hasConversation = false;
  let personalizedMode = false;
  let workProfile = {
    province: null as string | null,
    employment_status: null as string | null,
    start_date: null as string | null,
    monthly_wage: null as number | null,
  };
  await page.route("**/auth/work-profile", async (route) => {
    if (route.request().method() === "PUT") {
      workProfile = route.request().postDataJSON() as typeof workProfile;
    } else if (route.request().method() === "DELETE") {
      workProfile = { province: null, employment_status: null, start_date: null, monthly_wage: null };
    }
    await route.fulfill({
      status: route.request().method() === "DELETE" ? 204 : 200,
      contentType: "application/json",
      body: route.request().method() === "DELETE" ? "" : JSON.stringify(workProfile),
    });
  });
  await page.route("**/chat/conversations/conv_e2e/personalized-mode", async (route) => {
    personalizedMode = Boolean((route.request().postDataJSON() as { personalized_mode: boolean }).personalized_mode);
    await route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ conversation_id: "conv_e2e", title: "Chat", created_at: "2026-07-24T10:00:00Z",
        updated_at: "2026-07-24T10:01:00Z", message_count: 2, personalized_mode: personalizedMode }),
    });
  });
  await page.route("**/chat/usage", (route) => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({ usage_date: "2026-09-27", timezone: "Asia/Jakarta", reset_at: new Date(Date.now() + 86_400_000).toISOString(), limit_tokens: 100000, prompt_tokens: 700, completion_tokens: 300, used_tokens: 1000, reserved_tokens: 0, remaining_tokens: 99000, estimated_tokens: 0 }),
  }));
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
                personalized_mode: personalizedMode,
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
        personalized_mode: personalizedMode,
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
    const requestPayload = route.request().postDataJSON() as Record<string, unknown>;
    personalizedMode = Boolean(requestPayload.personalized_mode);
    onRequest?.(requestPayload);
    const response = {
      conversation_id: "conv_e2e",
      answer,
      latency_ms: 42,
      retrieval_score: refusal ? null : 0.95,
      token_usage: { prompt_tokens: 0, completion_tokens: 0 },
      reasoning_mode: requestPayload.reasoning_mode ?? "standard",
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
    if (message.type() === "error" && !message.text().includes("status of 401") && !message.text().includes("status of 403"))
      errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}

async function mockEmptyHistory(page: Page) {
  await page.route("**/chat/conversations", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });
}

async function mockGuestSession(page: Page) {
  await page.route("**/api/backend/auth/session", (route) =>
    route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Not authenticated" }),
    })
  );
  await page.route("**/auth/refresh", (route) =>
    route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Not authenticated" }),
    })
  );
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
  await expect(page.getByText("Sisa kuota hari ini:")).toBeVisible();
  await expect(page.getByRole("button", { name: "Mode jawaban" })).toContainText("Standar");
  await page.getByLabel("Ketik pertanyaan Anda").fill("Apakah pekerja PKWT memperoleh kompensasi?");
  await expect(page.getByRole("button", { name: "Kirim" })).toBeEnabled();
  await page.getByLabel("Ketik pertanyaan Anda").press("Enter");

  await expect(
    page.getByRole("main").getByText("Pekerja PKWT berhak memperoleh uang kompensasi.")
  ).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".editorial-answer-content > p")).toHaveCount(1);
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
  await page.getByRole("button", { name: /Lihat sumber.*1 sumber resmi/ }).click();
  await expect(page.getByText("Peraturan Pemerintah Nomor 35 Tahun 2021")).toBeVisible();
  await expect(page.getByRole("link", { name: /Buka PDF dokumen/ })).toBeVisible();
  await expect(page.getByRole("complementary").getByText(/Pasal 15.*Ayat \(1\)/)).toBeVisible();
  await expect(
    page.getByRole("complementary").getByText(citation.quote, { exact: true })
  ).toBeVisible();
  await expect(page.getByRole("link", { name: /Buka PDF dokumen/ })).toHaveAttribute(
    "href",
    /\/documents\/PP-35-2021\/pdf#page=12$/
  );
  const desktopSourceScreenshot = join(tmpdir(), "kerjapedia-chatgpt-desktop-source.png");
  await page.screenshot({ path: desktopSourceScreenshot });
  await page.setViewportSize({ width: 1280, height: 768 });
  const laptopSourceScreenshot = join(tmpdir(), "kerjapedia-chatgpt-laptop-source.png");
  await page.screenshot({ path: laptopSourceScreenshot });
  expect(runtimeErrors).toEqual([]);
  const desktopScreenshot = join(tmpdir(), "kerjapedia-chat-desktop.png");
  await page.screenshot({ path: desktopScreenshot });
  await testInfo.attach("sourced-answer", {
    path: desktopScreenshot,
    contentType: "image/png",
  });
});

test("user can switch and persist the answer mode", async ({ page }) => {
  let submittedMode: unknown;
  await useAuthenticatedSession(page);
  await mockChat(page, false, null, undefined, (payload) => {
    submittedMode = payload.reasoning_mode;
  });
  await page.goto("/");

  const mode = page.getByRole("button", { name: "Mode jawaban" });
  await expect(page.getByText("Sisa kuota hari ini:")).toBeVisible();
  await expect(mode).toContainText("Standar");
  await mode.click();
  await expect(page.getByText(/Analisis lebih rinci/)).toBeVisible();
  await page.getByRole("menuitemradio", { name: /Mendalam/ }).click();
  await expect(mode).toContainText("Mendalam");
  await expect(page.getByText(/Analisis lebih rinci/)).toBeHidden();
  await page.screenshot({ path: join(tmpdir(), "kerjapedia-chat-reasoning-mode.png") });
  await page.reload();
  await expect(mode).toContainText("Mendalam");

  await page.getByLabel("Ketik pertanyaan Anda").fill("Jelaskan aturan kompensasi PKWT");
  await page.getByRole("button", { name: "Kirim" }).click();

  await expect.poll(() => submittedMode).toBe("deep");
  await expect(page.getByText("Pekerja PKWT berhak memperoleh uang kompensasi.")).toBeVisible();
});

test("personalized mode keeps work facts and conversation choice", async ({ page }) => {
  test.setTimeout(90_000);
  let submitted: Record<string, unknown> | null = null;
  await useAuthenticatedSession(page);
  await mockChat(page, false, null, undefined, (payload) => { submitted = payload; });
  await page.goto("/");

  await page.getByRole("button", { name: "Atur profil kerja" }).click();
  await page.getByLabel("Provinsi tempat kerja").selectOption("Jawa Barat");
  await page.getByLabel("Hubungan kerja").selectOption("PKWT");
  await page.getByLabel("Tanggal mulai kerja").fill("2025-01-01");
  await page.getByLabel("Upah bulanan (Rp)").fill("5000000");
  await page.getByRole("button", { name: "Simpan profil" }).click();
  await page.getByLabel("Personalized Mode").check();
  await expect(page.getByText(/Jawa Barat .* PKWT/)).toBeVisible();

  await page.getByLabel("Ketik pertanyaan Anda").fill("Berapa THR saya?");
  await page.getByRole("button", { name: "Kirim" }).click();
  await expect.poll(() => submitted?.personalized_mode).toBe(true);
  await page.reload();
  await page.getByRole("region", { name: "Percakapan" }).getByRole("button", {
    name: "Apakah pekerja PKWT memperoleh kompensasi?", exact: true,
  }).click();
  await expect(page.getByLabel("Personalized Mode")).toBeChecked();
  await expect(page.getByText(/Jawa Barat .* PKWT/)).toBeVisible();
  await page.getByLabel("Personalized Mode").uncheck();
  await expect(page.getByLabel("Personalized Mode")).not.toBeChecked();
});

test("desktop sidebar collapses and persists", async ({ page }, testInfo) => {
  await mockGuestSession(page);
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
  await expect(page.locator("aside").first()).toBeVisible();
  await expect(page.locator("aside").first()).toHaveCSS("width", "64px");
  await expect(page.locator("aside").first().getByText("Chat baru")).toBeHidden();
  await expect(
    page.getByRole("navigation", { name: "Navigasi sidebar ringkas" }).getByRole("link", { name: "KerjaPedia AI beranda" })
  ).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Navigasi sidebar ringkas" }).getByRole("button", { name: "Percakapan baru" })
  ).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Navigasi sidebar ringkas" }).getByRole("button", { name: "Cari chat" })
  ).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Navigasi sidebar ringkas" }).getByRole("button", { name: "Masuk" })
  ).toBeVisible();
  const collapsedSidebarScreenshot = join(tmpdir(), "kerjapedia-sidebar-collapsed.png");
  await page.screenshot({ path: collapsedSidebarScreenshot });
  await testInfo.attach("sidebar-collapsed", {
    path: collapsedSidebarScreenshot,
    contentType: "image/png",
  });
  await page.reload();
  await expect(page.getByRole("button", { name: "Buka sidebar" })).toBeVisible();
  await expect(page.locator("aside").first()).toHaveCSS("width", "64px");
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
  await expect(profileMenu.getByRole("menuitem", { name: "Profil" })).toBeFocused();
  const profileMenuScreenshot = join(tmpdir(), "kerjapedia-profile-menu.png");
  await page.screenshot({ path: profileMenuScreenshot });
  await testInfo.attach("profile-menu", {
    path: profileMenuScreenshot,
    contentType: "image/png",
  });
  await profileMenu.getByRole("menuitem", { name: "Keluar" }).click();
  await page.getByRole("dialog", { name: "Keluar dari akun?" }).getByRole("button", { name: "Ya, keluar" }).click();

  await expect(page.getByRole("heading", { name: "Dapatkan jawaban yang sesuai untuk Anda" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Daftar gratis" })).toBeVisible();
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem("kerjapedia-session-v1")))
    .toBeNull();
});

test("guest conversation history is not shown or persisted in the sidebar", async ({ page }) => {
  await mockGuestSession(page);
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

  await expect(page.getByRole("heading", { name: "Dapatkan jawaban yang sesuai untuk Anda" })).toBeVisible();
  await expect(page.getByText("Percakapan guest lama")).toBeHidden();
  await expect(page.getByRole("button", { name: "Masuk", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Daftar gratis" })).toBeVisible();
  await expect(page.getByText("Apa yang ingin Anda pahami?")).toBeVisible();
});

test("guest authenticates through the two-step modal", async ({ page }, testInfo) => {
  test.setTimeout(60_000);
  await mockGuestSession(page);
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
  await expect(dialog.getByRole("button", { name: /Lanjutkan dengan Google/ })).toBeVisible();
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
  await passwordInput.fill("Kuat#2026Ragam");
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
    password: "Kuat#2026Ragam",
  });
  await expect(page.getByRole("button", { name: "Buka menu profil Pengguna Modal" })).toBeVisible();
  await expect(page.getByText("Pengguna Modal")).toHaveCount(1);
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem("kerjapedia-session-v1")))
    .toBeNull();
});

test("auth modal fits a mobile viewport", async ({ page }, testInfo) => {
  await mockGuestSession(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Buka menu" }).click();
  await page.getByRole("dialog", { name: "KerjaPedia Menu" }).getByRole("button", { name: "Masuk" }).click();

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
  await mockGuestSession(page);
  await page.goto("/");
  const trigger = page.getByRole("button", { name: "Masuk" }).last();
  await trigger.click();
  await expect(page.getByRole("dialog", { name: "Masuk ke KerjaPedia" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Masuk ke KerjaPedia" })).toBeHidden();
  await expect(trigger).toBeFocused();

  await page.getByRole("button", { name: "Daftar gratis" }).click();
  await expect(page.getByRole("dialog", { name: "Buat akun KerjaPedia" })).toBeVisible();
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

  await page.getByText("Hak kompensasi pekerja PKWT").hover();
  await page.getByRole("button", { name: /Tindakan untuk Hak kompensasi/ }).click();
  await page.getByRole("menuitem", { name: "Ubah judul" }).click();
  await page.getByLabel("Ubah judul percakapan").fill("Kompensasi PKWT");
  await page.getByRole("button", { name: "Simpan" }).click();
  await expect(page.getByText("Kompensasi PKWT")).toBeVisible();

  await page.getByText("Kompensasi PKWT").hover();
  await page.getByRole("button", { name: "Tindakan untuk Kompensasi PKWT" }).click();
  await page.screenshot({ path: join(tmpdir(), "kerjapedia-chat-history-actions.png") });
  await page.getByRole("menuitem", { name: "Hapus percakapan" }).click();
  await page.getByRole("dialog", { name: "Hapus percakapan" }).getByRole("button", { name: "Hapus percakapan" }).click();
  await expect(
    page.getByText("Belum ada percakapan. Ajukan pertanyaan pertama Anda.")
  ).toBeVisible();

  await testInfo.attach("history-actions", {
    path: join(tmpdir(), "kerjapedia-chat-history-actions.png"),
    contentType: "image/png",
  });
});

test("user sees a refusal when context is insufficient", async ({ page }, testInfo) => {
  await mockGuestSession(page);
  const runtimeErrors = monitorRuntimeErrors(page);
  await mockChat(page, true);
  await page.goto("/chat");
  await expect(page.locator("header")).toHaveAttribute("aria-busy", "false", { timeout: 20_000 });

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
  await mockGuestSession(page);
  const refusal =
    "Maaf, saya tidak tahu untuk pertanyaan tersebut. KerjaPedia AI difokuskan khusus pada regulasi dan persoalan ketenagakerjaan Indonesia.";
  await mockChat(page, true, "out_of_scope_query", refusal);
  await page.goto("/chat");
  await expect(page.locator("header")).toHaveAttribute("aria-busy", "false", { timeout: 20_000 });

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
  await mockGuestSession(page);
  await mockChat(page);
  await page.goto("/");
  await expect(page.getByText("Sisa kuota hari ini:")).toBeVisible();

  await page.getByLabel("Ketik pertanyaan Anda").fill("Apakah pekerja PKWT memperoleh kompensasi?");
  await page.getByRole("button", { name: "Kirim" }).click();
  await page.getByRole("button", { name: /Lihat sumber.*1 sumber resmi/ }).click();

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
  await mockGuestSession(page);
  await mockChat(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await mockEmptyHistory(page);
  await page.goto("/chat");

  await expect(page).toHaveURL(/\/chat$/);
  await expect(page.getByText("Sisa kuota hari ini:")).toBeVisible();
  const menuButton = page.getByRole("button", { name: "Buka menu" });
  await menuButton.click();
  await expect(menuButton).toHaveAttribute("aria-expanded", "true");
  const menuDialog = page.locator('aside[role="dialog"][aria-label="KerjaPedia Menu"]');
  await expect(menuDialog).toBeVisible();
  await expect(menuDialog.getByRole("button", { name: "Tutup riwayat" })).toBeFocused();
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
  await mockGuestSession(page);
  await page.goto("/chat");
  await expect(page.locator("header")).toHaveAttribute("aria-busy", "false", { timeout: 20_000 });

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
  await mockGuestSession(page);
  await mockEmptyHistory(page);
  await page.route("**/chat/ask/stream", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Jawaban belum dapat dimuat. Periksa koneksi Anda, lalu coba lagi." }),
    });
  });
  await page.goto("/chat");
  await expect(page.locator("header")).toHaveAttribute("aria-busy", "false", { timeout: 20_000 });

  await page.getByLabel("Ketik pertanyaan Anda").fill("Apa aturan waktu kerja?");
  await page.getByRole("button", { name: "Kirim" }).click();

  await expect(
    page.getByRole("alert").filter({ hasText: "Jawaban belum dapat dimuat. Periksa koneksi Anda, lalu coba lagi." })
  ).toBeVisible();
});

test("guest conversation continues and is saved after login", async ({ page }) => {
  let authenticated = false;
  let claimed = false;
  await page.route("**/api/backend/auth/session", (route) =>
    route.fulfill({
      status: authenticated ? 200 : 401,
      contentType: "application/json",
      body: authenticated
        ? JSON.stringify({
            user: {
              user_id: "user_claim",
              email: "user@example.com",
              name: "Pengguna Chat",
              roles: ["user"],
            },
          })
        : JSON.stringify({ detail: "No active session." }),
    })
  );
  await page.route("**/auth/login", (route) => {
    authenticated = true;
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        user: {
          user_id: "user_claim",
          email: "user@example.com",
          name: "Pengguna Chat",
          roles: ["user"],
        },
      }),
    });
  });
  await page.route("**/chat/conversations/conv_e2e/claim", (route) => {
    claimed = true;
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        conversation_id: "conv_e2e",
        title: "Apakah pekerja PKWT memperoleh kompensasi?",
        created_at: "2026-07-24T10:00:00Z",
        updated_at: "2026-07-24T10:01:00Z",
        message_count: 2,
      }),
    });
  });
  await mockChat(page);
  await page.goto("/chat");

  await page.getByLabel("Ketik pertanyaan Anda").fill("Apakah pekerja PKWT memperoleh kompensasi?");
  await page.getByRole("button", { name: "Kirim" }).click();
  await expect(
    page.getByRole("main").getByText("Pekerja PKWT berhak memperoleh uang kompensasi.")
  ).toBeVisible();

  await page.getByRole("button", { name: "Masuk", exact: true }).last().click();
  const dialog = page.getByRole("dialog", { name: "Masuk ke KerjaPedia" });
  await dialog.getByLabel("Alamat email").fill("user@example.com");
  await dialog.getByRole("button", { name: "Lanjutkan", exact: true }).click();
  await dialog.getByRole("textbox", { name: "Password" }).fill("Kuat#2026Ragam");
  await dialog.getByRole("button", { name: "Masuk", exact: true }).click();

  await expect.poll(() => claimed).toBe(true);
  await expect(
    page.getByRole("main").getByText("Pekerja PKWT berhak memperoleh uang kompensasi.")
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Percakapan" }).getByRole("button", {
      name: "Apakah pekerja PKWT memperoleh kompensasi?",
      exact: true,
    })
  ).toBeVisible();
});

test("chat layout remains usable from phone to desktop", async ({ page }) => {
  await page.route("**/api/backend/auth/session", (route) =>
    route.fulfill({ status: 401, contentType: "application/json", body: "{}" })
  );
  await page.route("**/auth/refresh", (route) =>
    route.fulfill({ status: 401, contentType: "application/json", body: "{}" })
  );
  await mockEmptyHistory(page);
  await page.goto("/chat");
  await expect(page.locator(".guest-shell")).toBeVisible();

  const viewports = [
    { width: 320, height: 568 },
    { width: 375, height: 667 },
    { width: 390, height: 844 },
    { width: 768, height: 1024 },
    { width: 1024, height: 768 },
    { width: 1440, height: 900 },
  ];
  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    const composer = page.getByLabel("Ketik pertanyaan Anda");
    await expect(composer).toBeVisible();
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth
        )
      )
      .toBeLessThanOrEqual(1);
    await expect
      .poll(async () => {
        const box = await composer.boundingBox();
        return box ? box.y + box.height : Infinity;
      })
      .toBeLessThanOrEqual(viewport.height);
    if ([320, 768, 1440].includes(viewport.width)) {
      await page.screenshot({ path: join(tmpdir(), `kerjapedia-chat-${viewport.width}.png`) });
    }
  }

  await page.setViewportSize({ width: 320, height: 568 });
  const menu = page.getByRole("button", { name: "Buka menu" });
  await expect(menu).toBeEnabled();
  await menu.click();
  const drawer = page.getByRole("dialog", { name: "KerjaPedia Menu" });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByRole("button", { name: "Masuk", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
  await expect(menu).toBeFocused();
});


test("initial chat fits without scrolling on a desktop viewport", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await mockGuestSession(page);
  await mockChat(page);
  await page.goto("/chat");

  await expect(page.getByRole("heading", { name: "Apa yang ingin Anda pahami?" })).toBeVisible();
  await expect(page.locator(".chat-suggestion")).toHaveCount(3);
  const initialChatOverflow = await page
    .getByLabel("Isi percakapan")
    .evaluate((region) => region.scrollHeight - region.clientHeight);
  expect(initialChatOverflow).toBeLessThanOrEqual(1);
});

test("guest sees daily quota on a narrow screen", async ({ page }) => {
  test.setTimeout(60_000);
  await page.setViewportSize({ width: 320, height: 700 });
  await mockGuestSession(page);
  await mockChat(page);
  await page.route("**/chat/usage", (route) => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({ usage_date: "2026-09-27", timezone: "Asia/Jakarta", reset_at: new Date(Date.now() + 86_400_000).toISOString(), limit_tokens: 20000, prompt_tokens: 1000, completion_tokens: 500, used_tokens: 1500, reserved_tokens: 0, remaining_tokens: 18500, estimated_tokens: 300 }),
  }));
  await page.goto("/chat");
  await expect(page.getByText(/Sisa kuota hari ini: 18\.500 dari 20\.000 token/)).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Penggunaan hari ini" })).toHaveAttribute("aria-valuenow", "1500");
  await expect(page.getByText("0/2.000 karakter")).toBeVisible();
  await expect(page.getByLabel("Ketik pertanyaan Anda")).toBeVisible();
  await expect(page.getByText("Asisten Hukum Ketenagakerjaan")).toHaveCount(0);
  const initialChatOverflow = await page
    .getByLabel("Isi percakapan")
    .evaluate((region) => region.scrollHeight - region.clientHeight);
  expect(initialChatOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: join(tmpdir(), "kerjapedia-chat-quota-mobile.png") });
  await page.getByRole("button", { name: "Mode jawaban" }).click();
  await expect(page.getByText("Untuk sebagian besar pertanyaan.")).toBeVisible();
  await page.screenshot({ path: join(tmpdir(), "kerjapedia-chat-mode-menu-mobile.png") });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

  await page.context().addCookies([
    { name: "settings-language", value: "en", url: new URL(page.url()).origin },
  ]);
  await page.reload();
  await expect(page.getByRole("heading", { name: "What would you like to understand?" })).toBeVisible();
  await expect(page.getByText("Employment Law Assistant")).toHaveCount(0);
  const englishOverflow = await page
    .getByLabel("Conversation content")
    .evaluate((region) => region.scrollHeight - region.clientHeight);
  expect(englishOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: join(tmpdir(), "kerjapedia-chat-empty-en-mobile.png") });
});

test("daily quota stays visible as a recoverable status when usage request fails", async ({ page }) => {
  await mockGuestSession(page);
  await mockChat(page);
  let attempts = 0;
  await page.route("**/chat/usage", (route) => {
    attempts += 1;
    if (attempts === 1) {
      return route.fulfill({ status: 503, contentType: "application/json", body: "{}" });
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        usage_date: "2026-09-27", timezone: "Asia/Jakarta",
        reset_at: new Date(Date.now() + 86_400_000).toISOString(),
        limit_tokens: 20000, prompt_tokens: 1000, completion_tokens: 500,
        used_tokens: 1500, reserved_tokens: 0, remaining_tokens: 18500,
        estimated_tokens: 0,
      }),
    });
  });
  await page.goto("/chat");
  await expect(page.getByText("Kuota belum dapat dimuat.")).toBeVisible();
  await page.getByRole("button", { name: "Coba lagi memuat kuota" }).click();
  await expect(page.getByText(/Sisa kuota hari ini: 18\.500 dari 20\.000 token/)).toBeVisible();
});

test("chat explains exhausted daily quota", async ({ page }) => {
  test.setTimeout(60_000);
  await mockGuestSession(page);
  await mockChat(page);
  await page.route("**/chat/ask/stream", (route) => route.fulfill({
    status: 429, contentType: "application/json",
    headers: { "Retry-After": "120" },
    body: JSON.stringify({ detail: { code: "daily_token_quota_exceeded", reset_at: new Date(Date.now() + 86_400_000).toISOString() } }),
  }));
  await page.goto("/chat");
  const input = page.getByLabel("Ketik pertanyaan Anda");
  await input.fill("Kapan THR dibayar?");
  await input.press("Enter");
  await expect(page.getByLabel("Isi percakapan").getByRole("alert")).toContainText(/Masuk atau daftar untuk mendapat kuota harian yang lebih besar/i);
  await expect(input).toHaveValue("Kapan THR dibayar?");
  await expect(page.getByRole("button", { name: /Kirim/i })).toBeDisabled();
});

test("chat reports quota exhaustion during processing", async ({ page }) => {
  await mockGuestSession(page);
  await mockChat(page);
  await page.route("**/chat/ask/stream", (route) => route.fulfill({
    status: 200,
    contentType: "application/x-ndjson",
    body: JSON.stringify({
      event: "error",
      code: "daily_token_quota_exceeded",
      detail: "Daily token quota was reached during processing.",
      reset_at: new Date(Date.now() + 86_400_000).toISOString(),
    }) + "\n",
  }));
  await page.goto("/chat");
  const input = page.getByLabel("Ketik pertanyaan Anda");
  await input.fill("Kapan THR dibayar?");
  await input.press("Enter");
  await expect(page.getByLabel("Isi percakapan").getByRole("alert")).toContainText(/kuota guest.*habis/i);
  await expect(input).toHaveValue("Kapan THR dibayar?");
  await expect(page.getByRole("button", { name: /Kirim/i })).toBeDisabled();
});
