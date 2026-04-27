import { expect, test } from "@playwright/test";

/**
 * Critical path: log in as the seeded organiser, create an event,
 * land on its details page, copy the public URL, open the public
 * sign-up form, submit it, verify the thanks state.
 *
 * Doesn't cover the email-driven verification flow (no SMTP in
 * tests) or admin approval (the seed pre-approves both fixture
 * users, which is exactly the path 99% of organisers take).
 */
test("organiser creates an event, public visitor signs up", async ({ browser }) => {
  // --- organiser: log in + create event ---
  const organiser = await browser.newContext();
  const page = await organiser.newPage();
  await page.goto("/login");
  await page.locator("input[type=email]").fill("organiser@local.dev");
  await page.locator("input[type=password]").fill("organiser1234");
  await page.locator("button[type=submit]").click();
  await page.waitForURL("**/dashboard");

  await page.getByRole("link", { name: /nieuw evenement|new event/i }).click();
  await page.locator("input[placeholder*='Naam'], input[placeholder*='Event name']").first().fill("E2E Smoke Event");
  await page.locator("input[placeholder*='Locatie'], input[placeholder*='Location']").fill("Amsterdam");
  // Date picker — pick today + 7 by typing into the day field.
  // PrimeVue DatePicker accepts free-text in dd-mm-yy; type a
  // hard-coded future date.
  await page.locator("input[placeholder*='Datum'], input[placeholder*='Date']").fill("31-12-26");
  await page.locator("button[type=submit]").click();
  await page.waitForURL("**/details", { timeout: 10_000 });
  // Public URL should be visible on the details overview.
  const publicLink = page
    .locator("a")
    .filter({ hasText: /\/e\// })
    .first();
  const slugUrl = await publicLink.getAttribute("href");
  expect(slugUrl).toBeTruthy();

  // --- visitor: open public link, sign up ---
  const visitor = await browser.newContext();
  const v = await visitor.newPage();
  await v.goto(slugUrl!);
  await v.locator("input").first().fill("Anna Anoniem");
  // Source select — PrimeVue Select; click + pick first option.
  await v.locator(".p-select").first().click();
  await v.locator(".p-select-option").first().click();
  await v.getByRole("button", { name: /aanmelden|sign up/i }).click();

  // Thanks state replaces the form.
  await expect(v.locator("h2")).toContainText(/bedankt|thanks/i);
});
