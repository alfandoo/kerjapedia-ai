import { expect, test, type Page } from "@playwright/test";

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

async function mockChat(page: Page, refusal = false) {
  await page.route("**/chat/ask", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        conversation_id: "conv_e2e",
        answer: {
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
          prompt_version_id: "kerjapedia-grounded-answer-v1",
          retrieved_chunk_ids: refusal ? [] : [citation.chunk_id],
          warnings: [],
        },
        latency_ms: 42,
        retrieval_score: refusal ? null : 0.95,
        token_usage: { prompt_tokens: 0, completion_tokens: 0 },
      }),
    });
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

test("user receives a sourced answer", async ({ page }, testInfo) => {
  const runtimeErrors = monitorRuntimeErrors(page);
  await mockChat(page);
  await page.goto("/");

  await expect(page).toHaveTitle("KerjaPedia AI");
  await expect(
    page.getByText(/Build Error|Runtime Error|Application error|Unhandled Runtime Error/i)
  ).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Tanya regulasi ketenagakerjaan" })).toBeVisible();
  await page.getByLabel("Ketik pertanyaan Anda").fill("Apakah pekerja PKWT memperoleh kompensasi?");
  await page.getByRole("button", { name: "Kirim" }).click();

  await expect(
    page.getByRole("main").getByText("Pekerja PKWT berhak memperoleh uang kompensasi.")
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /PP 35\/2021/ })).toBeVisible();
  await expect(page.getByText("Pasal 15", { exact: true })).toBeVisible();
  expect(runtimeErrors).toEqual([]);
  await testInfo.attach("sourced-answer", {
    body: await page.screenshot(),
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
  await expect(page.getByText("insufficient_retrieval_context")).toBeVisible();
  expect(runtimeErrors).toEqual([]);
  await testInfo.attach("refusal", {
    body: await page.screenshot(),
    contentType: "image/png",
  });
});
