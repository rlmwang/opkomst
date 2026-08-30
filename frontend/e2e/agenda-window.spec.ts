import { expect, test } from "@playwright/test";

/**
 * The agenda's rolling window is the organisation's to set.
 *
 * An admin opens ``/rsp/settings``, widens "show ahead" past an event
 * that sits beyond the current window, and the event appears on its
 * chapter's public agenda. That is the whole loop the setting exists
 * for: the occurrence was always materialised, only unshown.
 *
 * The window is restored at the end so the rest of the suite (and the
 * dev database it shares) sees the defaults it started with.
 */
const DEFAULTS = { agenda_future_days: 31, agenda_past_days: 60 };

test("an admin widens the agenda window and a far-off event appears", async ({
  request,
  browser,
  page,
}) => {
  const adminRes = await request.post("/api/v1/auth/dev-issue-token", {
    data: { email: "admin@local.dev", tenant: "rsp" },
  });
  expect(adminRes.ok()).toBeTruthy();
  const { token } = await adminRes.json();
  const auth = { Authorization: `Bearer ${token}` };

  const organiserRes = await request.post("/api/v1/auth/dev-issue-token", {
    data: { email: "organiser@local.dev", tenant: "rsp" },
  });
  const { token: orgToken, user } = await organiserRes.json();
  const chapterId = user.chapters[0].id as string;

  const chaptersRes = await request.get("/api/v1/chapters", { headers: auth });
  const chapters = (await chaptersRes.json()) as { id: string; slug: string }[];
  const chapterSlug = chapters.find((c) => c.id === chapterId)!.slug;

  // Start from the defaults whatever a previous run left behind.
  await request.put("/api/v1/settings", { headers: auth, data: DEFAULTS });

  // 48 days out: past the 31-day window, well inside a 90-day one.
  const startsAt = new Date(Date.now() + 48 * 24 * 60 * 60 * 1000);
  const name = `E2E Window ${startsAt.getTime()}`;
  const created = await request.post("/api/v1/event", {
    headers: { Authorization: `Bearer ${orgToken}` },
    data: {
      chapter_id: chapterId,
      name_nl: name,
      location: "Utrecht",
      starts_on: startsAt.toISOString().slice(0, 10),
      start_time: "20:00:00",
      end_time: "22:00:00",
      source_options: [{ label: "Mond-tot-mond" }],
      source_enabled: true,
      help_options: [],
      feedback_enabled: false,
      reminder_enabled: false,
      listed: true,
      locale: "nl",
    },
  });
  expect(created.ok()).toBeTruthy();

  // Each visit gets its own context: the agenda response carries a
  // public Cache-Control, and a visitor who already loaded the page is
  // not the reader this is about.
  const visit = async () => {
    const ctx = await browser.newContext();
    const v = await ctx.newPage();
    await v.goto(`/rsp/${chapterSlug}`);
    return v;
  };

  try {
    // --- outside the window: the agenda does not show it ---
    const before = await visit();
    await expect(before.getByText(name)).toHaveCount(0);

    // --- the admin widens it, in the UI ---
    await page.addInitScript((t) => {
      localStorage.setItem("token:rsp", t);
    }, token);
    await page.goto("/rsp/settings");

    const ahead = page.getByRole("spinbutton", { name: /vooruit tonen|show ahead/i });
    await expect(ahead).toHaveValue("31");
    await ahead.fill("90");
    await ahead.blur();
    // Wait for the write itself, not just the click. Reloading straight
    // after raced it: the page came back showing 31 because the PUT had
    // not landed yet, which read as the save being broken.
    const saved = page.waitForResponse(
      (r) => r.url().includes("/api/v1/settings") && r.request().method() === "PUT",
    );
    await page.getByRole("button", { name: /opslaan|save/i }).click();
    expect((await saved).ok()).toBeTruthy();

    // The saved value survives a reload, so it reached the server.
    await page.reload();
    await expect(
      page.getByRole("spinbutton", { name: /vooruit tonen|show ahead/i }),
    ).toHaveValue("90");

    // --- inside the window: the card is there ---
    const after = await visit();
    await expect(after.getByRole("heading", { name })).toBeVisible({ timeout: 5_000 });
  } finally {
    await request.put("/api/v1/settings", { headers: auth, data: DEFAULTS });
  }
});
