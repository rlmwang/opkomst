import { expect, test } from "@playwright/test";

/**
 * The boot spinner has to go away.
 *
 * Every shell paints one inside ``#app`` so a slow connection shows
 * something before the bundle lands, and it is ``position: fixed``
 * across the whole viewport. Vue's ``mount`` replaced the container's
 * children; Svelte's appends to them, so an entry that mounts without
 * clearing the container leaves the spinner on top of the page, hiding
 * what rendered underneath and swallowing every click.
 *
 * That shipped twice, once on the public pages and once on the
 * organiser app. Both times every other test still passed, because a
 * test that only asserts on the DOM does not notice a lid over it. This
 * is the test that notices.
 */
test("the shell clears its boot spinner", async ({ browser, request }) => {
  const loginRes = await request.post("/api/v1/auth/dev-issue-token", {
    data: { email: "organiser@local.dev", tenant: "rsp" },
  });
  expect(loginRes.ok()).toBeTruthy();
  const { token } = await loginRes.json();

  const context = await browser.newContext();
  await context.addInitScript((t) => window.localStorage.setItem("token:rsp", t), token as string);
  const page = await context.newPage();

  // The organiser app, and one page behind the auth guard: the guard
  // awaits ``/auth/me`` before the first render, which is the path that
  // leaves the spinner up longest.
  for (const path of ["/rsp", "/rsp/event", "/rsp/chore"]) {
    await page.goto(path);
    await expect(page.locator(".app-boot"), `boot spinner still on ${path}`).toHaveCount(0);
    await expect(page.locator(".app-loading"), `app spinner stuck on ${path}`).toHaveCount(0);
  }

  await context.close();
});
