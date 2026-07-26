import { expect, test } from "@playwright/test";
import { join } from "node:path";
import { tmpdir } from "node:os";

const documents = [
  {
    document_id: "UU-13-2003",
    title: "Undang-Undang Nomor 13 Tahun 2003 tentang Ketenagakerjaan",
    short_title: "UU 13/2003",
    regulation_type: "UU",
    number: 13,
    year: 2003,
    legal_status: "needs_verification",
    topics: ["hubungan_kerja", "phk"],
    source_url: "https://peraturan.bpk.go.id/",
    pdf_url: "/documents/PP-35-2021/pdf",
  },
  {
    document_id: "PP-35-2021",
    title: "Peraturan Pemerintah Nomor 35 Tahun 2021",
    short_title: "PP 35/2021",
    regulation_type: "PP",
    number: 35,
    year: 2021,
    legal_status: "active",
    topics: ["pkwt", "phk"],
    source_url: "https://peraturan.bpk.go.id/",
    pdf_url: "/documents/UU-13-2003/pdf",
  },
];

test.beforeEach(async ({ page }) => {
  await page.addInitScript((mockDocuments) => {
    const originalFetch = window.fetch.bind(window);
    window.fetch = (input, init) => {
      const url =
        typeof input === "string" ? input : input instanceof Request ? input.url : input.href;
      if (url === "http://127.0.0.1:8000/documents") {
        return Promise.resolve(
          new Response(JSON.stringify(mockDocuments), {
            status: 200,
            headers: { "content-type": "application/json" },
          })
        );
      }
      return originalFetch(input, init);
    };
  }, documents);
});

test("search page filters and resets the regulation list", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/search");

  await expect(page.getByRole("heading", { name: "Temukan dasar hukum yang tepat" })).toBeVisible();
  await expect(page.getByText("2 regulasi ditemukan")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByLabel("Riwayat percakapan")).toHaveCount(0);
  await expect(page.getByLabel("Sumber dan kutipan")).toHaveCount(0);

  await page.getByLabel("Cari judul, nomor, atau topik regulasi").fill("PKWT");
  await expect(page.getByText("1 regulasi ditemukan")).toBeVisible();
  await expect(page.getByText("Peraturan Pemerintah Nomor 35 Tahun 2021")).toBeVisible();
  await page.getByRole("button", { name: "Reset pencarian" }).click();
  await expect(page.getByText("2 regulasi ditemukan")).toBeVisible();

  await page.screenshot({ path: join(tmpdir(), "kerjapedia-search-landing-desktop.png") });
});

test("search page has a readable mobile layout and empty state", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/search");

  await page.getByLabel("Cari judul, nomor, atau topik regulasi").fill("tidak ditemukan");
  await expect(page.getByRole("heading", { name: "Regulasi tidak ditemukan" })).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByRole("button", { name: "Hapus filter" })).toBeVisible();
  await page.getByRole("button", { name: "Hapus filter" }).click();
  await expect(page.getByText("2 regulasi ditemukan")).toBeVisible();

  await page.screenshot({ path: join(tmpdir(), "kerjapedia-search-landing-mobile.png") });
});
