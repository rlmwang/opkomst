import { expect, test } from "@playwright/test";

/**
 * Critical path: public visitor lands on a real event's sign-up page,
 * fills the form, submits, sees the thanks state.
 *
 * The event is created via the organiser API rather than the form
 * UI — exercising the date-picker / location-autocomplete is its own
 * concern and would belong to an organiser-form spec, not the
 * public-flow critical path. The seed already pre-approves the
 * organiser, so the API call works without admin intervention.
 *
 * Doesn't cover the email-driven flows (no SMTP in tests).
 */
test("public visitor signs up for an event and sees the thanks state", async ({
  request,
  browser,
}) => {
  // --- arrange: log in as organiser, create an event via the API ---
  const loginRes = await request.post("/api/v1/auth/login", {
    data: { email: "organiser@local.dev", password: "organiser1234" },
  });
  expect(loginRes.ok()).toBeTruthy();
  const { token } = await loginRes.json();
  expect(token).toBeTruthy();

  // Far enough in the future that the reminder window doesn't fire
  // and the public form treats it as upcoming.
  const startsAt = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000); // +30d
  const endsAt = new Date(startsAt.getTime() + 2 * 60 * 60 * 1000); // +2h

  const eventRes = await request.post("/api/v1/events", {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name: "E2E Smoke Event",
      location: "Amsterdam",
      starts_at: startsAt.toISOString().slice(0, 19),
      ends_at: endsAt.toISOString().slice(0, 19),
      source_options: ["Mond-tot-mond"],
      help_options: [],
      questionnaire_enabled: false,
      reminder_enabled: false,
      locale: "nl",
    },
  });
  expect(eventRes.ok()).toBeTruthy();
  const event = await eventRes.json();
  expect(event.slug).toBeTruthy();

  // --- act: visitor opens the public link, fills + submits the form ---
  const visitor = await browser.newContext();
  const v = await visitor.newPage();
  await v.goto(`/e/${event.slug}`);

  // Display name input is the first field on the form.
  await v.locator("input").first().fill("Anna Anoniem");

  // Source select — PrimeVue Select; click + pick first option.
  await v.locator(".p-select").first().click();
  await v.locator(".p-select-option").first().click();

  await v.getByRole("button", { name: /aanmelden|sign up/i }).click();

  // --- assert: thanks state replaces the form ---
  // Multiple h2s on the page (the always-rendered "Help ons leren"
  // section sits below the form). Match by accessible name so the
  // locator picks exactly the thanks heading.
  await expect(
    v.getByRole("heading", { level: 2, name: /bedankt|thanks/i }),
  ).toBeVisible({ timeout: 5_000 });
});
