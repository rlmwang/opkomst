import { expect, test } from "@playwright/test";

/**
 * Critical path for the kompas (``docs/design-kompas.md``), in two
 * halves, because the two halves fail differently.
 *
 * **The organiser's page**, driven through the UI rather than the API:
 * the axes block and the per-answer pole selects are the whole of what
 * a kompas adds to the question editor, and an API-only test would
 * never touch either. It also checks the refusal that arrives before
 * the request, in Dutch, naming the question.
 *
 * **The public walk**, one question at a time, ending on the map. What
 * matters there is that the directions are not in the page before the
 * result, that the position comes from the server, and that "change
 * your answers" reopens the walk rather than starting a second one.
 */

/** Kill the transitions on a page that is about to be driven through a
 *  dozen PrimeVue Selects.
 *
 *  Each overlay animates in, and Playwright waits for a click target to
 *  be *stable* before clicking it. On a quiet machine that costs
 *  milliseconds; on a pre-push, where this runs beside the backend
 *  suite and the production build, the animation stretches and the
 *  waits add up until the test's own budget is gone. Removing the
 *  animation removes the flake at its source rather than widening the
 *  window it fits through. */
async function stopAnimating(page: import("@playwright/test").Page) {
  await page.addStyleTag({
    content: "*, *::before, *::after { transition: none !important; animation: none !important; }",
  });
}

/** Open one ``SelectField`` and choose an option by its label. The
 *  panel is a portal, so the option is found on the page rather than
 *  inside the select, and the panel has to be gone before the next one
 *  opens or the two overlap. */
async function pickPole(
  page: import("@playwright/test").Page,
  select: import("@playwright/test").Locator,
  label: string,
) {
  await select.click();
  await page.getByRole("option", { name: label, exact: true }).click();
  await expect(page.locator(".ovl-panel")).toHaveCount(0);
}

async function organiserToken(request: import("@playwright/test").APIRequestContext) {
  const res = await request.post("/api/v1/auth/dev-issue-token", {
    data: { email: "organiser@local.dev", tenant: "rsp" },
  });
  expect(res.ok()).toBeTruthy();
  return res.json();
}

test("organiser builds a kompas in the editor, and the refusals name the question", async ({
  browser,
  request,
}) => {
  const { token } = await organiserToken(request);

  const context = await browser.newContext({ reducedMotion: "reduce" });
  // The app reads its session from localStorage, keyed per
  // organisation (``api/client.ts``), so it is placed before the first
  // navigation rather than logged in through the form.
  await context.addInitScript((t) => window.localStorage.setItem("token:rsp", t), token as string);
  const page = await context.newPage();
  await page.goto("/rsp/compass/new");
  await stopAnimating(page);

  // ``exact``: the accessible-name match is a substring by default, and
  // the page has other headings with "assen" inside a longer word.
  await expect(page.getByRole("heading", { name: "Assen", exact: true })).toBeVisible({ timeout: 10_000 });

  await page.getByPlaceholder("Titel").fill("E2E Kompas");
  // An organiser in more than one chapter has to say which, the same
  // as on every other create page.
  await page.locator(".form-section .ovl-field").first().click();
  await page.getByRole("option").first().click();
  await expect(page.locator(".ovl-panel")).toHaveCount(0);

  // The two axes and their four sides. Every one of them is named,
  // because the result screen builds a sentence out of them.
  const axisCards = page.locator(".axis-card");
  await axisCards.nth(0).getByPlaceholder(/^Naam, bijvoorbeeld/).fill("Economie");
  await axisCards.nth(0).getByPlaceholder("Bijvoorbeeld: Links").fill("Links");
  await axisCards.nth(0).getByPlaceholder("Bijvoorbeeld: Rechts").fill("Rechts");
  await axisCards.nth(1).getByPlaceholder(/^Naam, bijvoorbeeld/).fill("Cultuur");
  await axisCards.nth(1).getByPlaceholder("Bijvoorbeeld: Progressief").fill("Open");
  await axisCards.nth(1).getByPlaceholder("Bijvoorbeeld: Conservatief").fill("Behoud");

  // Question one: a statement. New questions start as one.
  await page.getByRole("button", { name: "Vraag toevoegen" }).click();
  const first = page.locator(".question-editor").nth(0);
  await first.getByPlaceholder(/vraag|question/i).fill("De overheid moet zelf huizen bouwen");

  // Saving now is refused before the request goes out, in Dutch, and
  // it says which question and what is missing.
  await page.getByRole("button", { name: "Kompas aanmaken" }).click();
  await expect(page.getByText(/Vraag 1: kies wat een 5 betekent/)).toBeVisible();

  // The pole select carries the organiser's own words, live from the
  // axes block above.
  await pickPole(page, first.locator(".ovl-field").last(), "Economie: Links");

  // Question two: a multiple-choice question, one direction per answer.
  await page.getByRole("button", { name: "Vraag toevoegen" }).click();
  const second = page.locator(".question-editor").nth(1);
  await pickPole(page, second.locator(".ovl-field").first(), "Meerkeuze");
  await second.getByPlaceholder(/vraag|question/i).fill("Waar moet het geld heen?");
  for (const option of ["Zorg", "Defensie"]) {
    // The add-row: type the option and press Enter, the same way an
    // organiser does it.
    await second.getByPlaceholder("Optie").fill(option);
    await second.getByPlaceholder("Optie").press("Enter");
  }
  const optionRows = second.locator(".option-row-pointed");
  await expect(optionRows).toHaveCount(2);
  await pickPole(page, optionRows.nth(0).locator(".ovl-field"), "Economie: Links");
  await pickPole(page, optionRows.nth(1).locator(".ovl-field"), "Cultuur: Behoud");

  await page.getByRole("button", { name: "Kompas aanmaken" }).click();

  // The details page, with the map card on it.
  await expect(page.getByRole("heading", { name: "De kaart" })).toBeVisible({ timeout: 10_000 });
  // Every count on this page is read next to the direction that
  // earned it.
  await expect(page.getByText("Economie: Links").first()).toBeVisible();
});

test("a visitor walks a kompas and lands on the map", async ({ browser, request }) => {
  const { token, user } = await organiserToken(request);
  const chapterId = user.chapters[0].id;

  const created = await request.post("/api/v1/compass", {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      chapter_id: chapterId,
      name_nl: "E2E Smoke Kompas",
      locale: "nl",
      axes: [
        {
          axis: "x",
          name: "Economie",
          low_name: "Links",
          high_name: "Rechts",
        },
        { axis: "y", name: "Cultuur", low_name: "Open", high_name: "Behoud" },
      ],
      questions: [
        {
          kind: "rating",
          prompt: "De overheid moet zelf huizen bouwen",
          pole: "x_low",
          low_label: "Oneens",
          high_label: "Eens",
        },
        {
          kind: "single_choice",
          prompt: "Waar moet het geld heen?",
          options: ["Zorg", "Defensie"],
          option_poles: ["x_low", "y_high"],
        },
      ],
    },
  });
  expect(created.ok()).toBeTruthy();
  const kompas = await created.json();

  const visitor = await browser.newContext();
  const v = await visitor.newPage();
  await v.goto(`/k/${kompas.slug}`);

  // The cover: what this places people on, and the sentence that is
  // the privacy contract of the feature.
  await expect(v.getByText(/Je naam komt op de kaart/)).toBeVisible({ timeout: 10_000 });
  await expect(v.getByText("Economie").first()).toBeVisible();
  await v.getByPlaceholder(/schuil|pseudo/i).fill("Anna Anoniem");
  await v.getByRole("button", { name: "Beginnen" }).click();

  // One question at a time, and no direction anywhere in the page.
  await expect(v.getByText("Vraag 1 van 2")).toBeVisible();
  await expect(v.getByText("Waar moet het geld heen?")).toHaveCount(0);
  await expect(v.getByText("Links", { exact: true })).toHaveCount(0);

  // A required question gates Next rather than the submit.
  await v.getByRole("button", { name: "Volgende" }).click();
  await expect(v.getByText(/Geef eerst een antwoord/)).toBeVisible();

  await v.locator(".dot", { hasText: "5" }).first().click();
  await v.getByRole("button", { name: "Volgende" }).click();
  await expect(v.getByText("Vraag 2 van 2")).toBeVisible();
  await v.getByRole("radio", { name: "Zorg" }).check();
  await v.getByRole("button", { name: "Klaar" }).click();

  // The map, then the sentence per axis in the organiser's own words,
  // then every answer with the direction it carried.
  await expect(v.getByRole("heading", { name: "Waar je staat" })).toBeVisible({ timeout: 10_000 });
  await expect(v.locator("circle.dot")).toHaveCount(1);
  await expect(v.getByText("Je staat aan de kant van Links")).toBeVisible();
  await expect(v.getByText(/Over deze as heb je niks ingevuld/)).toBeVisible();
  await expect(v.getByText(/Een 5 was Links, jij zei 5/)).toBeVisible();

  // The token is in the URL, so a refresh reopens the map rather than
  // starting the kompas again.
  await expect(v).toHaveURL(/\/k\/[^/?]+\?s=/);
  await v.reload();
  await expect(v.getByRole("heading", { name: "Waar je staat" })).toBeVisible({ timeout: 10_000 });

  // And changing your mind is allowed, unlike a quiz.
  await v.getByRole("button", { name: "Verander je antwoorden" }).click();
  await expect(v.getByText("Vraag 1 van 2")).toBeVisible();
});
