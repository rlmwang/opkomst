import { expect, test } from "@playwright/test";

/**
 * The welcome tour, end to end: the one test that proves the tour and
 * the app agree. Sign in as the seeded organiser who has not been
 * offered the tour, press Start on the card, and do what each of the
 * five steps says, ending on a details page with the overlay gone and
 * the card gone for good.
 *
 * The welcome tour keeps its declared list, so its counter is the one
 * place a dropped step would show: "5 van 5" on the last step is the
 * assertion that nothing was dropped.
 */
test("a new organiser takes the welcome tour to their first event", async ({ browser, request }) => {
  const forget = await request.post("/api/v1/auth/dev-forget-tour-offer", {
    data: { email: "organiser@local.dev", tenant: "rsp" },
  });
  expect(forget.ok()).toBeTruthy();
  const login = await request.post("/api/v1/auth/dev-issue-token", {
    data: { email: "organiser@local.dev", tenant: "rsp" },
  });
  const { token } = await login.json();

  const context = await browser.newContext({ viewport: { width: 1024, height: 768 } });
  await context.addInitScript((t) => window.localStorage.setItem("token:rsp", t), token as string);
  const page = await context.newPage();

  await page.goto("/rsp/");
  const card = page.getByRole("heading", { name: "Nieuw hier?" });
  await expect(card).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Start de rondleiding" }).click();

  const callout = page.getByRole("dialog").filter({ hasText: "van 5" });

  // 1: the events tile.
  await expect(callout).toContainText("1 van 5");
  await page.getByRole("link", { name: /^Evenement/ }).first().click();

  // 2: Nieuw evenement.
  await expect(callout).toContainText("2 van 5", { timeout: 15_000 });
  await page.getByRole("button", { name: "Nieuw evenement" }).click();

  // 3: the form. A name, a chapter and a date, then Evenement aanmaken.
  await expect(callout).toContainText("3 van 5", { timeout: 15_000 });
  await page.getByPlaceholder("Titel").fill("E2E Rondleiding");
  await page.locator(".form-section .ovl-field").first().click();
  await page.getByRole("option").first().click();
  const date = new Date(Date.now() + 14 * 24 * 60 * 60 * 1000);
  const dd = String(date.getDate()).padStart(2, "0");
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dateField = page.getByPlaceholder("Datum");
  await dateField.fill(`${dd}-${mm}-${date.getFullYear()}`);
  await dateField.press("Tab");
  await page.getByRole("button", { name: "Evenement aanmaken" }).click();

  // 4: the share link on the details page.
  await expect(callout).toContainText("4 van 5", { timeout: 20_000 });
  await expect(page).toHaveURL(/\/rsp\/event\/[^/]+\/details/);
  await page.getByRole("button", { name: "Volgende" }).click();

  // 5: the menu, and Klaar.
  await expect(callout).toContainText("5 van 5");
  await page.getByRole("button", { name: "Klaar" }).click();
  await expect(page.locator(".tour-callout")).toHaveCount(0);
  await expect(page.locator(".tour-mask")).toHaveCount(0);

  // The card does not come back.
  await page.goto("/rsp/");
  await expect(page.getByRole("heading", { name: "Nieuw hier?" })).toHaveCount(0);
  await expect(page.locator(".tile-grid")).toBeVisible();

  await context.close();
});
