import { expect, test, type Page } from "@playwright/test";

const dataset = {
  dataset_id: "evalset_live",
  name: "Golden questions",
  questions: [
    {
      question_id: "EVAL-001",
      category: "pkwt",
      question: "Apakah pekerja PKWT memperoleh kompensasi?",
      expected_answer: "Ya.",
      expected_document_ids: ["PP-35-2021"],
      expected_articles: ["Pasal 15"],
      expected_topics: ["pkwt"],
      should_refuse: false,
      hard_negative: false,
      status: "verified",
    },
  ],
  created_at: "2026-09-21T00:00:00Z",
};

async function mockEvaluationApi(page: Page) {
  await page.route("**/api/backend/auth/session", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        user: {
          user_id: "admin_e2e",
          email: "admin@example.com",
          name: "Admin Demo",
          roles: ["user", "admin"],
        },
      }),
    })
  );
  await page.route("**/api/backend/evaluation/datasets", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([dataset]),
    })
  );
  await page.route("**/api/backend/evaluation/runs", async (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          run_id: "evalrun_live",
          dataset_id: dataset.dataset_id,
          release_id: null,
          status: "pending",
          progress_completed: 0,
          progress_total: 4,
          error: null,
          created_at: "2026-09-21T00:00:00Z",
          metrics: {},
        }),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: "[]",
    });
  });
}

test("Upstash live evaluation always runs four ranking strategies", async ({ page }) => {
  await mockEvaluationApi(page);
  await page.goto("/admin/evaluation");

  await page.getByRole("button", { name: "Jalankan evaluasi" }).click();
  const dialog = page.getByRole("dialog", { name: "Jalankan evaluasi" });

  await expect(dialog.getByText("Sumber retrieval")).toBeVisible();
  await expect(dialog.getByText("Upstash live")).toBeVisible();
  await expect(dialog.getByText("Mode eksperimen")).toHaveCount(0);
  for (const mode of ["Baseline", "Dense", "Hybrid", "Re-ranker"]) {
    await expect(dialog.getByText(mode, { exact: true })).toBeVisible();
  }

  const runRequest = page.waitForRequest(
    (request) =>
      request.url().endsWith("/api/backend/evaluation/runs") && request.method() === "POST"
  );
  await dialog.getByRole("button", { name: "Jalankan evaluasi" }).click();

  expect((await runRequest).postDataJSON()).toEqual({
    dataset_id: dataset.dataset_id,
    experiment_modes: ["upstash"],
    top_k: 5,
  });
});
