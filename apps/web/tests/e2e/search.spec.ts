import { expect, test, type Page } from "@playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";

const documents = [
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
    pdf_url: "/documents/PP-35-2021/pdf",
  },
  {
    document_id: "UU-13-2003",
    title: "Undang-Undang Nomor 13 Tahun 2003 tentang Ketenagakerjaan",
    short_title: "UU 13/2003",
    regulation_type: "UU",
    number: 13,
    year: 2003,
    legal_status: "needs_verification",
    topics: ["upah", "hubungan_kerja"],
    source_url: "https://peraturan.bpk.go.id/",
    pdf_url: "/documents/UU-13-2003/pdf",
  },
];

async function mockDocuments(page: Page) {
  await page.route("**/documents", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(documents),
    });
  });
}

test("search filters the regulation catalog", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockDocuments(page);
  await page.goto("/search");

  await expect(page.getByRole("heading", { name: "Temukan dasar hukum yang tepat" })).toBeVisible();
  await expect(page.getByText("2 regulasi ditemukan")).toBeVisible();
  await expect(page.getByText("Jenis regulasi")).toBeVisible();

  await page.getByLabel("Cari judul, nomor, atau topik regulasi").fill("35");
  await expect(page.getByText("1 regulasi ditemukan")).toBeVisible();
  await expect(page.getByRole("heading", { name: /Peraturan Pemerintah Nomor 35/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Undang-Undang Nomor 13/ })).toBeHidden();
  await expect(page.getByRole("link", { name: "Buka PDF PP 35/2021" })).toHaveAttribute(
    "href",
    /\/documents\/PP-35-2021\/pdf$/
  );

  await page.screenshot({ path: join(tmpdir(), "kerjapedia-search-desktop-final.png") });
});

test("search remains readable on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockDocuments(page);
  await page.goto("/search");

  await expect(page.getByText("Jenis regulasi")).toBeHidden();
  await expect(page.getByRole("heading", { name: /Peraturan Pemerintah Nomor 35/ })).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth
      )
    )
    .toBe(true);

  await page.screenshot({ path: join(tmpdir(), "kerjapedia-search-mobile-final.png") });
});
