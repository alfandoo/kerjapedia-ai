import { expect, test, type Page } from "@playwright/test";

const adminSession = {
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
  await page.route("**/api/backend/auth/session", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(adminSession),
    })
  );
}

test("stored session hydrates the chat shell without mismatch", async ({ page }) => {
  const runtimeErrors = monitorRuntimeErrors(page);
  await preloadAdminSession(page);

  await page.goto("/");

  await expect(page.getByRole("button", { name: "Buka menu profil Admin Demo" })).toBeVisible();
  await expect(page.getByRole("link", { name: "KerjaPedia AI beranda" })).toContainText("KerjaPedia AI");
  const sidebarBrand = page.getByRole("link", { name: "KerjaPedia AI beranda" }).locator("strong");
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

  await page.context().addCookies([{
    name: "kp-access",
    value: "mock-admin-access",
    url: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3100",
    httpOnly: true,
    sameSite: "Lax",
  }]);
  await page.goto("/admin/dashboard");

  await expect(page.getByRole("link", { name: "Dashboard" })).toBeVisible();
  expect(runtimeErrors.filter((error) => /hydration|server rendered text/i.test(error))).toEqual(
    []
  );
});
