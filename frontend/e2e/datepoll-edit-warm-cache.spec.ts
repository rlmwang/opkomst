import { expect, test } from "@playwright/test";

/**
 * Regression: opening the datepoll edit page with the poll already in the
 * Query cache (navigating in from the details page, a client-side route
 * change) used to crash. The edit page's ``immediate`` data watch fires
 * synchronously during setup, which set ``selectedDates`` before the
 * ``flush: "sync"`` buffer watcher populated ``newSlot[iso]`` — the
 * day-card add-row then read ``undefined``. (Earlier it threw a TDZ on
 * ``draftRestored`` in the same warm path.) Exercise details → edit.
 */
test("editing a datepoll from its details page (warm cache) renders", async ({ request, browser }) => {
  const loginRes = await request.post("/api/v1/auth/dev-issue-token", {
    data: { email: "organiser@local.dev", tenant: "rsp" },
  });
  expect(loginRes.ok()).toBeTruthy();
  const { token, user } = await loginRes.json();
  const chapterId = user.chapters[0].id;

  const pollRes = await request.post("/api/v1/datepolls", {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name_nl: "E2E Warm-cache Poll",
      chapter_id: chapterId,
      locale: "nl",
      slots: [{ on_date: "2027-09-01" }, { on_date: "2027-09-02" }],
    },
  });
  expect(pollRes.ok()).toBeTruthy();
  const poll = await pollRes.json();

  // Log the browser in (the app reads the JWT from localStorage).
  const ctx = await browser.newContext();
  await ctx.addInitScript((t) => window.localStorage.setItem("token", t), token as string);
  const page = await ctx.newPage();

  // Load the details page first — this warms the useDatepoll cache.
  await page.goto(`/rsp/datepolls/${poll.id}/details`);
  await expect(page.getByRole("heading", { name: "E2E Warm-cache Poll" })).toBeVisible({ timeout: 10_000 });

  // Client-side navigate into edit: the poll is served from the warm cache.
  await page.locator(`a[href="/rsp/datepolls/${poll.id}/edit"]`).click();

  // The per-day add-row (its time inputs) proves the day-cards rendered
  // without the newSlot crash.
  await expect(page.locator(".time-input").first()).toBeVisible({ timeout: 10_000 });
  await ctx.close();
});
