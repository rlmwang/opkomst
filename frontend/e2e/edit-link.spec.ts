import { expect, test } from "@playwright/test";

/**
 * Edit-link critical path: a visitor signs up, the confirmation shows
 * a magic edit link, and reopening that link pre-fills the prior
 * answer and lets them change it. Proves the ``?s={token}`` round-trip
 * end-to-end through the real mini-app (token surfaced once, reusable
 * while the event is open). Mirrors ``critical-path.spec.ts`` for the
 * organiser-API setup.
 */
test("visitor edits a signup via the magic link on the confirmation page", async ({
  request,
  browser,
}) => {
  const loginRes = await request.post("/api/v1/auth/dev-issue-token", {
    data: { email: "organiser@local.dev" },
  });
  expect(loginRes.ok()).toBeTruthy();
  const { token, user } = await loginRes.json();
  const chapterId = user.chapters[0].id;

  const startsAt = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000);
  const endsAt = new Date(startsAt.getTime() + 2 * 60 * 60 * 1000);
  const eventRes = await request.post("/api/v1/events", {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name: "E2E Edit-link Event",
      chapter_id: chapterId,
      location: "Amsterdam",
      starts_at: startsAt.toISOString().slice(0, 19),
      ends_at: endsAt.toISOString().slice(0, 19),
      source_options: ["Mond-tot-mond"],
      help_options: [],
      feedback_enabled: false,
      reminder_enabled: false,
      locale: "nl",
    },
  });
  expect(eventRes.ok()).toBeTruthy();
  const event = await eventRes.json();

  const visitor = await browser.newContext();
  const v = await visitor.newPage();
  await v.goto(`/e/${event.slug}`);

  await v.locator("input").first().fill("Anna Anoniem");
  const sourceTrigger = v.locator("button[aria-haspopup='listbox']");
  await expect(sourceTrigger).toBeEnabled({ timeout: 5_000 });
  await sourceTrigger.click();
  await v.locator("[role='option']").filter({ hasText: "Mond-tot-mond" }).click();
  await v.getByRole("button", { name: /aanmelden|sign up/i }).click();

  await expect(v.getByRole("heading", { level: 2, name: /bedankt|thanks/i })).toBeVisible({
    timeout: 5_000,
  });

  // The edit link is the readonly field inside the EditLink card.
  const editUrl = await v.locator(".link-field").inputValue();
  expect(editUrl).toContain(`/e/${event.slug}?s=`);

  // --- reopen the link: prior answer pre-filled, editable ---
  const e = await visitor.newPage();
  await e.goto(editUrl);
  await expect(e.locator("input").first()).toHaveValue("Anna Anoniem", { timeout: 5_000 });

  await e.locator("input").first().fill("Anna Bijgewerkt");
  await e.getByRole("button", { name: /aanmelden|sign up/i }).click();
  await expect(e.getByRole("heading", { level: 2, name: /bedankt|thanks/i })).toBeVisible({
    timeout: 5_000,
  });
  // Same token still resolves (reusable while the event is open).
  await expect(e.locator(".link-field")).toHaveValue(editUrl);
});
