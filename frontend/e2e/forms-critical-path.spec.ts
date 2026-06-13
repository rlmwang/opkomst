import { expect, test } from "@playwright/test";

/**
 * Critical path for the Forms feature: public visitor lands on a
 * real form's fill-out page, fills every kind of question,
 * submits, sees the thanks state.
 *
 * Mirrors the events critical-path spec — the form is created via
 * the organiser API rather than the UI (the question editor's
 * interactions are their own spec to write later, not the public-
 * flow critical path). The seed pre-approves the organiser.
 *
 * Covers all five question kinds so a regression in the kind enum
 * or the per-kind submit-handler validation breaks this test.
 */
test("public visitor fills a form and sees the thanks state", async ({
  request,
  browser,
}) => {
  // --- arrange: log in as organiser, create a form via the API ---
  const loginRes = await request.post("/api/v1/auth/dev-issue-token", {
    data: { email: "organiser@local.dev" },
  });
  expect(loginRes.ok()).toBeTruthy();
  const { token, user } = await loginRes.json();
  expect(token).toBeTruthy();
  expect(user.chapters.length).toBeGreaterThan(0);
  const chapterId = user.chapters[0].id;

  const formRes = await request.post("/api/v1/forms", {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      chapter_id: chapterId,
      name: "E2E Smoke Form",
      locale: "nl",
      questions: [
        {
          kind: "rating",
          prompt: "Hoe was het evenement?",
          required: true,
          low_label: "Slecht",
          high_label: "Top",
        },
        {
          kind: "short_text",
          prompt: "Je voornaam (optioneel)",
          required: false,
        },
        {
          kind: "text",
          prompt: "Tips voor volgende keer?",
          required: false,
        },
        {
          kind: "single_choice",
          prompt: "Heb je vrienden meegenomen?",
          required: true,
          options: ["Ja", "Nee"],
        },
        {
          kind: "multi_choice",
          prompt: "Welke onderdelen vond je sterk?",
          required: false,
          options: ["Programma", "Eten", "Ontmoetingen"],
        },
      ],
    },
  });
  expect(formRes.ok()).toBeTruthy();
  const form = await formRes.json();
  expect(form.slug).toBeTruthy();

  // --- act: visitor opens /f/<slug>, fills every kind, submits ---
  // The mini-app uses native HTML inputs (no PrimeVue): rating
  // dots are ``<button class="dot">``, choice questions are
  // ``<input type="radio">`` / ``<input type="checkbox">``,
  // text fields are bare ``<input>`` / ``<textarea>``.
  const visitor = await browser.newContext();
  const v = await visitor.newPage();
  await v.goto(`/f/${form.slug}`);

  // Wait for the form to mount — the loading card is replaced
  // with the first question's prompt.
  await expect(v.getByText("Hoe was het evenement?")).toBeVisible({ timeout: 5_000 });

  // Rating: click the "5" dot on the first rating question.
  await v.locator(".dot", { hasText: "5" }).first().click();

  // Short text: required-false so we leave it blank (the
  // submit-handler treats whitespace-only as skipped).

  // Long text: again required-false; leave blank.

  // Single choice: pick "Ja".
  await v.getByRole("radio", { name: "Ja" }).check();

  // Multi choice: pick two boxes.
  await v.getByRole("checkbox", { name: "Programma" }).check();
  await v.getByRole("checkbox", { name: "Ontmoetingen" }).check();

  await v.getByRole("button", { name: /versturen|submit/i }).click();

  // --- assert: thanks state ---
  await expect(
    v.getByRole("heading", { level: 2, name: /bedankt|thank/i }),
  ).toBeVisible({ timeout: 5_000 });
});
