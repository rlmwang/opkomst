import { expect, test } from "@playwright/test";

/**
 * Opening a dropdown must not scroll the page.
 *
 * A panel is moved to the end of ``<body>`` and positioned against the
 * viewport, so nothing inside it has any business moving the document.
 * Two things did: ``scrollIntoView`` on the row the panel opens on,
 * which scrolls every scrollable ancestor and not only the list, and
 * ``focus`` on the filter box, which scrolls whatever it has to. A
 * field near the bottom edge therefore took the whole page with it.
 *
 * Proven to catch it: with the old ``scrollIntoView`` and a plain
 * ``focus`` put back, this measures a 376 px jump.
 */
test("opening a dropdown near the bottom edge does not scroll the page", async ({
  browser,
  request,
}) => {
  const res = await request.post("/api/v1/auth/dev-issue-token", {
    data: { email: "organiser@local.dev", tenant: "rsp" },
  });
  const { token } = await res.json();
  const context = await browser.newContext({ viewport: { width: 900, height: 700 } });
  await context.addInitScript((t) => window.localStorage.setItem("token:rsp", t), token as string);
  const page = await context.newPage();

  await page.goto("/rsp/event/new");
  await page.waitForSelector(".ovl-field");
  // The form settles: the chapter list lands and the draft is restored,
  // both of which change its height.
  await page.waitForTimeout(1500);

  // The language select is the last one on the form. Put it near the
  // bottom edge, so its panel hangs below the fold.
  const field = page.locator(".ovl-field").last();
  await page.evaluate(() => {
    const els = document.querySelectorAll(".ovl-field");
    const el = els[els.length - 1] as HTMLElement;
    window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - window.innerHeight + 90);
  });
  await page.waitForTimeout(200);

  const before = await page.evaluate(() => window.scrollY);
  expect(before, "the page has to be scrolled for this to prove anything").toBeGreaterThan(100);

  await field.click({ force: true });
  await page.waitForSelector(".ovl-panel");
  await page.waitForTimeout(250);

  const after = await page.evaluate(() => window.scrollY);
  expect(after, "the page moved when the panel opened").toBe(before);

  await context.close();
});
