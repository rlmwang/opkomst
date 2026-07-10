import { expect, test } from "@playwright/test";

/**
 * Public chapter agenda: a visitor opens ``/e/{chapter}`` and sees a
 * grid of the chapter's upcoming events, each linking to its sign-up
 * page. An ``listed: false`` event is created too and must NOT appear.
 *
 * Events are created via the organiser API (the seed pre-approves the
 * organiser). Names carry the ``E2E `` prefix so the cleanup teardown
 * sweeps them.
 */
test("visitor browses the chapter agenda and signs up from a card", async ({
  request,
  browser,
}) => {
  const loginRes = await request.post("/api/v1/auth/dev-issue-token", {
    data: { email: "organiser@local.dev" },
  });
  expect(loginRes.ok()).toBeTruthy();
  const { token, user } = await loginRes.json();
  const chapterId = user.chapters[0].id;

  // Resolve the chapter's public slug (the agenda lives at /e/{slug}).
  const chaptersRes = await request.get("/api/v1/chapters", {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(chaptersRes.ok()).toBeTruthy();
  const chapters = (await chaptersRes.json()) as { id: string; slug: string }[];
  const chapter = chapters.find((c) => c.id === chapterId);
  expect(chapter?.slug).toBeTruthy();

  const startsAt = new Date(Date.now() + 20 * 24 * 60 * 60 * 1000); // +20d
  const endsAt = new Date(startsAt.getTime() + 2 * 60 * 60 * 1000);
  const base = {
    chapter_id: chapterId,
    location: "Amsterdam",
    starts_on: startsAt.toISOString().slice(0, 10),
    start_time: "19:00:00",
    end_time: "21:00:00",
    source_options: ["Mond-tot-mond"],
    help_options: [],
    feedback_enabled: false,
    reminder_enabled: false,
    locale: "nl",
  };
  const uniq = `${startsAt.getTime()}`;
  const listedName = `E2E Agenda Listed ${uniq}`;
  const hiddenName = `E2E Agenda Hidden ${uniq}`;

  const listedRes = await request.post("/api/v1/events", {
    headers: { Authorization: `Bearer ${token}` },
    data: { ...base, name_nl: listedName, listed: true },
  });
  expect(listedRes.ok()).toBeTruthy();
  const listed = await listedRes.json();
  // The agenda card + public page key on the OCCURRENCE slug now.
  const listedOccRes = await request.get(`/api/v1/events/${listed.id}/occurrences`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const listedOccSlug = (await listedOccRes.json()).occurrences[0].slug as string;

  const hiddenRes = await request.post("/api/v1/events", {
    headers: { Authorization: `Bearer ${token}` },
    data: { ...base, name_nl: hiddenName, listed: false },
  });
  expect(hiddenRes.ok()).toBeTruthy();

  // --- act: visitor opens the chapter agenda ---
  const visitor = await browser.newContext();
  const v = await visitor.newPage();
  await v.goto(`/e/${chapter!.slug}`);

  // The listed event's card is visible; the unlisted one is absent.
  await expect(v.getByRole("heading", { name: listedName })).toBeVisible({
    timeout: 5_000,
  });
  await expect(v.getByText(hiddenName)).toHaveCount(0);

  // The sign-up CTA in that card deep-links to the event's page.
  await v
    .locator("article")
    .filter({ hasText: listedName })
    .getByRole("link", { name: /aanmelden|sign up/i })
    .click();
  await expect(v).toHaveURL(new RegExp(`/e/${listedOccSlug}`));
});
