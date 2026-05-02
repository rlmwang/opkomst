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
  // ``/auth/dev-issue-token`` is the LOCAL_MODE=1 test fixture
  // that mints a JWT without the magic-link round-trip. Returns
  // 404 in any other environment so prod can't call it.
  const loginRes = await request.post("/api/v1/auth/dev-issue-token", {
    data: { email: "organiser@local.dev" },
  });
  expect(loginRes.ok()).toBeTruthy();
  const { token, user } = await loginRes.json();
  expect(token).toBeTruthy();
  // Pick the first chapter from the organiser's membership set —
  // multi-chapter membership made ``chapter_id`` a required body
  // field on event create, and the seed gives the organiser at
  // least one chapter.
  expect(user.chapters.length).toBeGreaterThan(0);
  const chapterId = user.chapters[0].id;

  // Far enough in the future that the reminder window doesn't fire
  // and the public form treats it as upcoming.
  const startsAt = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000); // +30d
  const endsAt = new Date(startsAt.getTime() + 2 * 60 * 60 * 1000); // +2h

  const eventRes = await request.post("/api/v1/events", {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name: "E2E Smoke Event",
      chapter_id: chapterId,
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
  // The page now lives in its own Vue mini-app
  // (``frontend/public-event.html`` + ``src/public/``) using
  // native ``<input>`` / ``<button>`` plus a custom
  // ``BrandedSelect`` component (button trigger + role=listbox
  // popup). Selectors below match that shape.
  const visitor = await browser.newContext();
  const v = await visitor.newPage();
  await v.goto(`/e/${event.slug}`);

  // Display name input is the first field on the form. The form
  // is form-first-rendered: this input is interactive even before
  // the by-slug fetch resolves.
  await v.locator("input").first().fill("Anna Anoniem");

  // Source dropdown — ``BrandedSelect`` renders a ``<button>``
  // with ``aria-haspopup="listbox"`` + a ``<ul role="listbox">``
  // popup. Trigger stays disabled until the event payload
  // arrives (so its options know which strings to render). Wait
  // for it to become enabled, click to open, then pick the
  // first non-placeholder option ("Mond-tot-mond").
  const sourceTrigger = v.locator("button[aria-haspopup='listbox']");
  await expect(sourceTrigger).toBeEnabled({ timeout: 5_000 });
  await sourceTrigger.click();
  await v.locator("[role='option']").filter({ hasText: "Mond-tot-mond" }).click();

  await v.getByRole("button", { name: /aanmelden|sign up/i }).click();

  // --- assert: thanks state replaces the form ---
  await expect(
    v.getByRole("heading", { level: 2, name: /bedankt|thanks/i }),
  ).toBeVisible({ timeout: 5_000 });
});
