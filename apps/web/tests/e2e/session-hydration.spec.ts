import { expect, test, type Page } from "@playwright/test";

const adminSession = {
  access_token: "e2e-admin-token",
  user: {
    user_id: "admin_e2e",
    email: "admin@example.com",
    name: "Admin Demo",
    roles: ["user", "admin"],
  },
};

function monitorRuntimeErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}

async function preloadAdminSession(page: Page) {
  await page.addInitScript((session) => {
    window.localStorage.setItem("kerjapedia-session-v1", JSON.stringify(session));
  }, adminSession);
}

test("stored session hydrates the chat shell without mismatch", async ({ page }) => {
  const runtimeErrors = monitorRuntimeErrors(page);
  await preloadAdminSession(page);

  await page.goto("/");

  await expect(page.locator(".chatgpt-account-avatar").first()).toHaveText("AD");
  await expect(page.locator(".chatgpt-account strong").first()).toHaveText("Admin Demo");
  await expect(
    page.locator(".desktop-sidebar").getByRole("link", { name: "KerjaPedia AI beranda" })
  ).toContainText("KerjaPedia AI");
  const sidebarBrand = page.locator(".desktop-sidebar .chatgpt-sidebar-brand-full strong");
  await expect(sidebarBrand).toBeVisible();
  await expect
    .poll(() => sidebarBrand.evaluate((element) => element.scrollWidth <= element.clientWidth))
    .toBe(true);
  expect(runtimeErrors.filter((error) => /hydration|server rendered text/i.test(error))).toEqual(
    []
  );
});

test("stored session hydrates the admin shell without mismatch", async ({ page }) => {
  const runtimeErrors = monitorRuntimeErrors(page);
  await preloadAdminSession(page);
  await page.route("**/admin/documents", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        summary: { documents: 0, published: 0, needs_review: 0, failed: 0 },
        documents: [],
      }),
    });
  });

  await page.goto("/admin");

  await expect(page.getByText("Admin Knowledge Base")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Knowledge Base" })).toBeVisible();
  expect(runtimeErrors.filter((error) => /hydration|server rendered text/i.test(error))).toEqual(
    []
  );
});
